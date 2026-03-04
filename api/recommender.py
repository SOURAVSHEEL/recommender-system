"""
recommender.py — Core RAG pipeline

Pipeline:
  1. Query expansion via Gemini
  2. Hybrid search — semantic (FAISS) + keyword (BM25) on expanded query
  3. Reciprocal Rank Fusion
  4. LLM reranker via Gemini (reranking.md) — selects & orders final results
  5. Return top-K results
"""

import json
import logging
import re
import time
import threading
import google.generativeai as genai
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from rank_bm25 import BM25Okapi

from api.config import (
    STORE_PATH, PROMPTS_DIR,
    GOOGLE_API_KEY, GOOGLE_API_KEY_2, GOOGLE_EMBED_MODEL, GEMINI_MODEL,
    TOP_K_SEMANTIC, TOP_K_KEYWORD, TOP_K_RERANK, TOP_K_FINAL,
)

log = logging.getLogger(__name__)

# ── Prompts ───────────────────────────────────────────────────────────────────

system_prompt    = (PROMPTS_DIR / "system.md").read_text(encoding="utf-8").strip()
expansion_prompt = (PROMPTS_DIR / "query_expansion.md").read_text(encoding="utf-8").strip()
reranking_prompt = (PROMPTS_DIR / "reranking.md").read_text(encoding="utf-8").strip()

# ── Gemini clients — two separate API keys to avoid rate-limit contention ─────
#
#   gemini_expansion : KEY_2  — query expansion  (short, fast, called once per request)
#   gemini_rerank    : KEY_1  — LLM reranker     (heavy, long context, called once per request)



# a threading Lock so concurrent requests don't overwrite each other's key.
genai_lock = threading.Lock()

EXPANSION = genai.GenerationConfig(temperature=1, max_output_tokens=4096)
RERANK    = genai.GenerationConfig(temperature=0, max_output_tokens=8192)


def call_expansion(prompt: str):
    """Call Gemini for query expansion using GOOGLE_API_KEY_2."""
    with genai_lock:
        genai.configure(api_key=GOOGLE_API_KEY_2)
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config=EXPANSION,
        )
        return model.generate_content(prompt)


def call_rerank(prompt: str):
    """Call Gemini for LLM reranking using GOOGLE_API_KEY."""
    with genai_lock:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config=RERANK,
        )
        return model.generate_content(prompt)

# ── Stopwords — remove noise words that hurt BM25 precision ──────────────────

STOPWORDS = {
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "by","from","is","are","was","were","be","been","being","have","has",
    "had","do","does","did","will","would","could","should","may","might",
    "i","we","you","he","she","they","it","my","our","your","their","its",
    "this","that","these","those","who","which","what","how","when","where",
    "can","also","not","no","as","if","so","all","some","any","each","than",
    "then","just","about","up","out","into","more","very","want","need",
    "looking","hiring","hire","find","recommend","suggest",
    "role","position","candidate","candidates",
    "company","work","working","experience","years","year",
    "long","max","maximum","duration","minutes","min","hour",
    "please","me","us","am","im","like","get","use","using","based","good",
}


def tokenize(text: str) -> list[str]:
    """Lowercase, split, remove stopwords and short tokens."""
    tokens = text.lower().split()
    return [t for t in tokens if t not in STOPWORDS and len(t) > 2]


# ── Query expansion via Gemini ────────────────────────────────────────────────

def strip_fences(text: str) -> str:
    """Remove markdown code fences wherever they appear in the text.

    Gemini sometimes adds prose before the fence, puts the fence on the same
    line as the JSON, or omits the closing newline — handle all cases.
    """
    text = text.strip()
    # Remove opening fence (with optional language tag and optional space/newline)
    text = re.sub(r"```[a-z]*[ \t]*\n?", "", text)
    # Remove closing fence
    text = re.sub(r"\n?```", "", text)
    return text.strip()


def sanitise_for_prompt(text: str) -> str:
    """
    Escape characters that cause JSON parse errors when Gemini echoes
    user-supplied text back inside a JSON string value.
    Replaces curly quotes, apostrophes in contractions, and stray backslashes.
    """
    # Replace curly / typographic apostrophes and quotes with straight versions
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    # Escape lone backslashes so they don't corrupt JSON
    text = text.replace("\\", "\\\\")
    # Replace unescaped apostrophes inside words (contractions) with a space
    # so Gemini doesn't try to include them verbatim in a JSON string
    text = re.sub(r"(?<=\w)\'(?=\w)", " ", text)
    return text


def _parse_expansion(raw: str) -> dict:
    """
    Robustly extract semantic + keywords from Gemini expansion response.

    Handles all observed failure modes:
      1. Perfect JSON                          -> json.loads
      2. Single-quoted Python dict             -> ast.literal_eval
      3. Truncated JSON (no closing brace)     -> regex field extraction
      4. Double braces {{...}}                 -> normalise then retry
    """
    import ast as _ast

    # Normalise double braces from old .format()-style prompts
    text = raw.replace("{{", "{").replace("}}", "}")

    # Attempt 1: standard JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: find complete {...} block and try again (handles prose wrapping)
    match = re.search(r'\{[^{}]*"semantic".*?"keywords".*?\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Attempt 3: ast.literal_eval for single-quoted dicts
    try:
        result = _ast.literal_eval(text)
        if isinstance(result, dict):
            return result
    except Exception:
        pass

    # Attempt 4: truncated response — extract values via regex directly
    # This fires when the response is cut off before the closing }
    semantic, keywords = "", ""
    m = re.search(r'"semantic"\s*:\s*"(.*?)(?:"|$)', text, re.DOTALL)
    if m:
        semantic = m.group(1).rstrip('"').strip()
    m = re.search(r'"keywords"\s*:\s*"(.*?)(?:"|$)', text, re.DOTALL)
    if m:
        keywords = m.group(1).rstrip('"').strip()

    if semantic and keywords:
        log.debug("Expansion parsed via field extraction (response was truncated)")
        return {"semantic": semantic, "keywords": keywords}

    raise ValueError(f"Could not parse expansion response: {raw[:120]!r}")


def expand_query(query: str) -> tuple[str, str]:
    """
    Calls Gemini with query_expansion.md prompt which returns JSON:
      {"semantic": "...", "keywords": "..."}

    Returns (semantic_query, keyword_query):
      - semantic: rich paragraph for FAISS vector search
      - keywords: short distilled phrase for BM25 keyword search

    Falls back to (query, query) on any error.
    """
    log.info("Expanding query via Gemini (%s) ...", GEMINI_MODEL)
    t0 = time.time()
    safe_query = sanitise_for_prompt(query)
    prompt = (
        system_prompt + "\n\n"
        + expansion_prompt.replace("{query}", safe_query)
    )
    try:
        response = call_expansion(prompt)
        raw = strip_fences(response.text)
        log.debug("Raw expansion response: %s", raw[:300])

        parsed = _parse_expansion(raw)

        semantic = parsed.get("semantic", "").strip()
        keywords = parsed.get("keywords", "").strip()
        if not semantic or not keywords:
            raise ValueError("Missing semantic or keywords field in expansion response")
        log.info(
            "Query expanded (%.2fs) — semantic: %d chars | keywords: %d chars",
            time.time() - t0, len(semantic), len(keywords),
        )
        log.info("Keywords: %s", keywords)
        return semantic, keywords
    except Exception as e:
        log.warning("Query expansion failed (%s) — falling back to original query", e)
        return query, query



vector_store : FAISS | None     = None
bm25         : BM25Okapi | None = None
bm25_metadata: list[dict]       = []


def get_vector_store() -> FAISS:
    global vector_store
    if vector_store is None:
        log.info("Loading FAISS vector store from: %s", STORE_PATH)
        t0 = time.time()
        embeddings = GoogleGenerativeAIEmbeddings(
            model=GOOGLE_EMBED_MODEL,
            google_api_key=GOOGLE_API_KEY,
            task_type="retrieval_query",
            transport="rest",  # avoid gRPC async channel in sync threadpool
        )
        vector_store = FAISS.load_local(
            str(STORE_PATH), embeddings, allow_dangerous_deserialization=True
        )
        log.info("FAISS store loaded — %d vectors (%.2fs)", vector_store.index.ntotal, time.time() - t0)
    return vector_store


def get_bm25() -> tuple[BM25Okapi, list[dict]]:
    global bm25, bm25_metadata
    if bm25 is None:
        log.info("Building BM25 index ...")
        t0 = time.time()
        docs = list(get_vector_store().docstore._dict.values())
        bm25_metadata = [doc.metadata for doc in docs]
        corpus = [
            tokenize(
                doc.metadata.get("name", "") + " "
                + " ".join(doc.metadata.get("job_levels", [])) + " "
                + " ".join(doc.metadata.get("test_types", []))
            )
            for doc in docs
        ]
        bm25 = BM25Okapi(corpus)
        log.info("BM25 index built — %d docs (%.2fs)", len(corpus), time.time() - t0)
    return bm25, bm25_metadata


# ── Search ────────────────────────────────────────────────────────────────────

def semantic_search(query: str) -> list[tuple[dict, int]]:
    docs = get_vector_store().similarity_search(query, k=TOP_K_SEMANTIC)
    log.info("Semantic search -> %d results", len(docs))
    return [(doc.metadata, rank) for rank, doc in enumerate(docs)]


def keyword_search(query: str) -> list[tuple[dict, int]]:
    bm25, metadata = get_bm25()
    scores  = bm25.get_scores(tokenize(query))
    top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:TOP_K_KEYWORD]
    log.info("BM25 search -> %d results", len(top_idx))
    return [(metadata[i], rank) for rank, i in enumerate(top_idx)]


def reciprocal_rank_fusion(
    semantic: list[tuple[dict, int]],
    keyword:  list[tuple[dict, int]],
    k: int = 60,
) -> list[dict]:
    scores: dict[str, float] = {}
    by_url: dict[str, dict]  = {}

    for meta, rank in semantic:
        url = meta["url"]
        scores[url] = scores.get(url, 0) + 1 / (k + rank + 1)
        by_url[url] = meta

    for meta, rank in keyword:
        url = meta["url"]
        scores[url] = scores.get(url, 0) + 1 / (k + rank + 1)
        by_url[url] = meta

    ranked = sorted(scores, key=lambda u: scores[u], reverse=True)
    log.info(
        "RRF fusion — semantic: %d, keyword: %d -> %d unique candidates",
        len(semantic), len(keyword), len(ranked),
    )
    return [by_url[url] for url in ranked]


# ── LLM Reranker ─────────────────────────────────────────────────────────────

def llm_rerank(query: str, candidates: list[dict]) -> list[dict]:
    """
    Send top candidates to Gemini for LLM-based relevance reranking.
    The prompt also enforces test_type diversity (K + P balance).
    Returns reordered subset of candidates.
    """
    if not candidates:
        return candidates

    slim = [
        {
            "url":             c["url"],
            "name":            c["name"],
            "description":     c["description"][:200],
            "test_types":      c["test_types"],
            "test_type_codes": c["test_type_codes"],
            "job_levels":      c["job_levels"],
            "duration":        c["duration"],
        }
        for c in candidates
    ]

    log.info("LLM reranking %d candidates via Gemini (%s) ...", len(slim), GEMINI_MODEL)
    t0 = time.time()
    try:
        prompt = (
            f"{system_prompt}\n\n"
            + reranking_prompt.format(
                query=query,
                candidates=json.dumps(slim, indent=2),
            )
            + "\n\nIMPORTANT: Reply with a JSON array of URL strings ONLY. "
              "No explanation, no code fences, no extra text."
        )
        response = call_rerank(prompt)
        raw = strip_fences(response.text)
        log.info("LLM reranker response (%.2fs), %d chars: %s", time.time() - t0, len(raw), raw[:300])

        # Extract JSON array even when Gemini wraps it in prose/explanation
        # Strategy: find the first "[" and the last "]" in the response
        array_start = raw.find("[")
        array_end   = raw.rfind("]")
        if array_start != -1 and array_end > array_start:
            raw = raw[array_start: array_end + 1]
        elif not raw.startswith("["):
            raise ValueError("No JSON array found in reranker response")

        # If the array appears truncated (no closing bracket found above won't
        # trigger, but inner URLs may be cut) — recover partial list
        if not raw.endswith("]"):
            log.warning("Reranker array appears truncated (%d chars) — attempting recovery", len(raw))
            last_complete = raw.rfind('",')
            if last_complete != -1:
                raw = raw[: last_complete + 1] + "\n]"
            else:
                raise ValueError("Cannot recover truncated reranker JSON")

        url_order = json.loads(raw)
        if not isinstance(url_order, list):
            raise ValueError("Expected JSON array of URLs")

        by_url   = {c["url"]: c for c in candidates}
        reranked = [by_url[url] for url in url_order if url in by_url]

        seen = set(url_order)
        for c in candidates:
            if c["url"] not in seen:
                reranked.append(c)

        log.info("LLM reranker -> %d ordered results", len(reranked))
        return reranked

    except Exception as e:
        log.warning("LLM reranker failed (%s) — falling back to RRF order", e)
        return candidates


# ── Duration filter ───────────────────────────────────────────────────────────

def extract_max_duration(query: str) -> int | None:
    """Parse max duration constraint from query text. Returns minutes or None."""
    q = query.lower()
    m = re.search(r"(?:max(?:imum)?|under|less\s+than|within|up\s+to)?\s*(\d+)\s*(?:min(?:utes?)?|mins?)\b", q)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(\d+)\s*hour", q)
    if m:
        return int(m.group(1)) * 60
    if "an hour" in q or "one hour" in q:
        return 60
    return None


# ── Seniority detection & filtering ──────────────────────────────────────────

JUNIOR_LEVELS  = {"Entry-Level", "Graduate"}
MID_LEVELS     = {"Mid-Professional", "Professional Individual Contributor", "General Population"}
MANAGER_LEVELS = {"Supervisor", "Front Line Manager", "Manager"}
SENIOR_LEVELS  = {"Director", "Executive"}

_SENIORITY_RULES: list[tuple[list[str], str]] = [
    (["coo", "ceo", "cto", "cfo", "c-suite", "chief operating", "chief executive",
      "chief technology", "chief financial", "vice president", " vp ", "evp", "svp",
      "president and", "managing director"],
     "senior"),
    (["director", "head of", "general manager"],
     "senior"),
    (["new graduate", "new graduates", "fresh graduate", "fresh graduates",
      "fresher", "entry level", "entry-level", "0-2 year", "0 to 2 year",
      "0 - 2 year", "0-2 year", "no experience", "0 years"],
     "junior"),
    (["graduate"],
     "junior"),
    (["manager", "team lead", "supervisor", "front line manager"],
     "manager"),
    (["senior ", "sr. ", "lead ", "mid-level", "mid level"],
     "mid"),
]


def detect_seniority(query: str) -> str | None:
    """Return 'junior' | 'mid' | 'manager' | 'senior' | None.

    For soft signals like 'manager' and 'graduate', only match against the
    first 150 chars (the user's own framing) to avoid false matches inside
    job description body text such as 'manager guidance' or 'graduate programme'.
    Strong executive / director titles are matched across the full query.
    """
    q_full  = " " + query.lower() + " "
    # Only the user's leading request text — avoids matching JD body
    q_short = " " + query[:150].lower() + " "

    # C-suite / executive — safe to match anywhere in full query
    for phrase in ["coo", "ceo", "cto", "cfo", "c-suite", "chief operating",
                   "chief executive", "chief technology", "chief financial",
                   "vice president", " vp ", "evp", "svp", "president and",
                   "managing director"]:
        if phrase in q_full:
            log.info("Seniority detected: senior")
            return "senior"

    # Director-level — full query safe
    for phrase in ["director", "head of", "general manager"]:
        if phrase in q_full:
            log.info("Seniority detected: senior")
            return "senior"

    # Junior — explicit phrases are unambiguous, safe anywhere
    for phrase in ["new graduate", "new graduates", "fresh graduate", "fresh graduates",
                   "fresher", "entry level", "entry-level", "0-2 year", "0 to 2 year",
                   "0 - 2 year", "0-2 year", "no experience", "0 years"]:
        if phrase in q_full:
            log.info("Seniority detected: junior")
            return "junior"

    # 'graduate' alone is ambiguous — only match in user's short prefix
    if "graduate" in q_short:
        log.info("Seniority detected: junior")
        return "junior"

    # Manager / team lead — short prefix only (avoids 'manager guidance' in JD body)
    for phrase in ["manager", "team lead", "supervisor", "front line manager"]:
        if phrase in q_short:
            log.info("Seniority detected: manager")
            return "manager"

    # Mid / senior IC — short prefix only
    for phrase in ["senior ", "sr. ", "lead ", "mid-level", "mid level"]:
        if phrase in q_short:
            log.info("Seniority detected: mid")
            return "mid"

    return None


def seniority_score(candidate: dict, tier: str) -> float:
    """
    +1.0  = level matches perfectly
     0.0  = level-agnostic (empty job_levels)
    -2.0  = clear opposite
    -0.5  = partial mismatch
    """
    levels = set(candidate.get("job_levels", []))
    if not levels:
        return 0.0

    if tier == "junior":
        if levels & JUNIOR_LEVELS:         return  1.0
        if levels.issubset(SENIOR_LEVELS): return -2.0
        return -0.5

    if tier == "senior":
        if levels & SENIOR_LEVELS:         return  1.0
        if levels.issubset(JUNIOR_LEVELS): return -2.0
        return -0.5

    if tier == "manager":
        if levels & MANAGER_LEVELS:        return  1.0
        if levels.issubset(JUNIOR_LEVELS): return -0.5
        return 0.0

    if tier == "mid":
        if levels & MID_LEVELS:            return  1.0
        if levels & SENIOR_LEVELS and not (levels & MID_LEVELS): return -0.5
        return 0.0

    return 0.0


# ── Public entry point ────────────────────────────────────────────────────────

def recommend(query: str) -> list[dict]:
    log.info("=== recommend() called ===")
    log.info("Query: %.120s%s", query, "..." if len(query) > 120 else "")

    max_duration = extract_max_duration(query)
    seniority    = detect_seniority(query)
    if max_duration:
        log.info("Duration constraint: <= %d minutes", max_duration)

    semantic_query, keyword_query = expand_query(query)
    log.info("Semantic query (%.80s%s)", semantic_query, "..." if len(semantic_query) > 80 else "")
    log.info("Keyword query: %s", keyword_query)
    t0         = time.time()
    semantic   = semantic_search(semantic_query)   # FAISS uses rich semantic paragraph
    keyword    = keyword_search(keyword_query)     # BM25 uses tight keyword phrase
    candidates = reciprocal_rank_fusion(semantic, keyword)
    log.info("Hybrid search done (%.2fs) — %d candidates", time.time() - t0, len(candidates))

    # ── Step 1: Duration hard filter ─────────────────────────────────────────
    if max_duration:
        before = len(candidates)
        candidates = [
            c for c in candidates
            if c.get("duration") is None or c["duration"] <= max_duration
        ]
        log.info("Duration filter (<=%d min): %d -> %d", max_duration, before, len(candidates))

    # ── Step 2: Seniority hard-exclude ───────────────────────────────────────
    if seniority:
        ACCEPT_FOR = {
            "junior": JUNIOR_LEVELS | MID_LEVELS,
            "senior": SENIOR_LEVELS | MANAGER_LEVELS,
        }
        accept = ACCEPT_FOR.get(seniority, set())
        if accept:
            before = len(candidates)
            hard_filtered = [
                c for c in candidates
                if not c.get("job_levels")
                or bool(set(c["job_levels"]) & accept)
            ]
            if len(hard_filtered) >= 5:
                candidates = hard_filtered
                log.info("Seniority hard-exclude (%s): %d -> %d", seniority, before, len(candidates))
            else:
                log.warning("Seniority hard-exclude would leave %d — skipping", len(hard_filtered))

    # ── Step 3: Seniority re-rank ─────────────────────────────────────────────
    if seniority:
        candidates = sorted(candidates, key=lambda c: seniority_score(c, seniority), reverse=True)
        log.info("Seniority re-ranked (%s) — top3: %s", seniority, [c["name"] for c in candidates[:3]])

    # ── Step 4: Guarantee minimum 5 results ──────────────────────────────────
    if len(candidates) < 5:
        log.warning("Only %d candidates — padding from unfiltered pool", len(candidates))
        all_cands = reciprocal_rank_fusion(semantic, keyword)
        seen = {c["url"] for c in candidates}
        for c in all_cands:
            if c["url"] not in seen:
                candidates.append(c)
                seen.add(c["url"])
            if len(candidates) >= 5:
                break

    # ── Step 5: LLM reranking on top candidates ───────────────────────────────
    rerank_pool = candidates[:TOP_K_RERANK]
    reranked    = llm_rerank(query, rerank_pool)

    results = [
        {
            "name":             c["name"],
            "url":              c["url"],
            "description":      c["description"],
            "duration":         c["duration"],
            "remote_support":   "Yes" if c["remote_testing"] else "No",
            "adaptive_support": "Yes" if c["adaptive"] else "No",
            "test_type":        c["test_types"],
        }
        for c in reranked[:TOP_K_FINAL]
    ]

    log.info("Returning %d assessments", len(results))
    return results