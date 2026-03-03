"""
recommender.py — Core RAG pipeline

Pipeline:
  1. Query expansion via Groq API 
  2. Hybrid search — semantic (FAISS) + keyword (BM25) on expanded query
  3. Reciprocal Rank Fusion
  4. LLM reranker via Groq (reranking.md) — selects & orders final results
  5. Return top-K results
"""

import json
import logging
import re
import time

from groq import Groq
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings
from rank_bm25 import BM25Okapi

from api.config import (
    STORE_PATH, PROMPTS_DIR,
    OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL,
    GROQ_API_KEY, GROQ_MODEL,
    TOP_K_SEMANTIC, TOP_K_KEYWORD, TOP_K_RERANK, TOP_K_FINAL,
)

log = logging.getLogger(__name__)

# ── Prompts ───────────────────────────────────────────────────────────────────

system_prompt    = (PROMPTS_DIR / "system.md").read_text(encoding="utf-8").strip()
expansion_prompt = (PROMPTS_DIR / "query_expansion.md").read_text(encoding="utf-8").strip()
reranking_prompt = (PROMPTS_DIR / "reranking.md").read_text(encoding="utf-8").strip()

# ── Groq client ───────────────────────────────────────────────────────────────

groq = Groq(api_key=GROQ_API_KEY)

# Stopwords — remove noise words that hurt BM25 precision
STOPWORDS = {
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "by","from","is","are","was","were","be","been","being","have","has",
    "had","do","does","did","will","would","could","should","may","might",
    "i","we","you","he","she","they","it","my","our","your","their","its",
    "this","that","these","those","who","which","what","how","when","where",
    "can","also","not","no","as","if","so","all","some","any","each","than",
    "then","just","about","up","out","into","more","very","want","need",
    "looking","hiring","hire","find","recommend","suggest","assessment",
    "assessments","test","tests","role","position","candidate","candidates",
    "company","team","business","work","working","experience","years","year",
    "new","level","long","max","maximum","duration","minutes","min","hour",
    "please","me","us","am","im","like","get","use","using","based","good",
}


def tokenize(text: str) -> list[str]:
    """Lowercase, split, remove stopwords and short tokens."""
    tokens = text.lower().split()
    return [t for t in tokens if t not in STOPWORDS and len(t) > 2]


# ── Query expansion via Groq ──────────────────────────────────────────────────

def expand_query(query: str) -> str:
    log.info("Expanding query via Groq (%s) ...", GROQ_MODEL)
    t0 = time.time()
    response = groq.chat.completions.create(
        model=GROQ_MODEL,
        temperature=0,
        max_tokens=300,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": expansion_prompt.format(query=query)},
        ],
    )
    expanded = response.choices[0].message.content.strip()
    log.info("Query expanded (%.2fs) — %d → %d chars", time.time() - t0, len(query), len(expanded))
    log.info("Expanded query: %s", expanded)
    return expanded


# ── Lazy singletons ───────────────────────────────────────────────────────────

vector_store : FAISS | None     = None
bm25         : BM25Okapi | None = None
bm25_metadata: list[dict]       = []


def get_vector_store() -> FAISS:
    global vector_store
    if vector_store is None:
        log.info("Loading FAISS vector store from: %s", STORE_PATH)
        t0 = time.time()
        embeddings = OllamaEmbeddings(model=OLLAMA_EMBED_MODEL, base_url=OLLAMA_BASE_URL)
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
        # BM25 corpus: name + job_levels + test_types (structured keyword fields)
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
    log.info("Semantic search → %d results", len(docs))
    return [(doc.metadata, rank) for rank, doc in enumerate(docs)]


def keyword_search(query: str) -> list[tuple[dict, int]]:
    bm25, metadata = get_bm25()
    scores  = bm25.get_scores(tokenize(query))
    top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:TOP_K_KEYWORD]
    log.info("BM25 search → %d results", len(top_idx))
    return [(metadata[i], rank) for rank, i in enumerate(top_idx)]


def reciprocal_rank_fusion(
    semantic: list[tuple[dict, int]],
    keyword:  list[tuple[dict, int]],
    k: int = 60,) -> list[dict]:
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
        "RRF fusion — semantic: %d, keyword: %d → %d unique candidates",
        len(semantic), len(keyword), len(ranked),
    )
    return [by_url[url] for url in ranked]


# ── LLM Reranker ─────────────────────────────────────────────────────────────

def llm_rerank(query: str, candidates: list[dict]) -> list[dict]:
    """
    Send top candidates to Groq for LLM-based relevance reranking.
    The prompt also enforces test_type diversity (K + P balance).
    Returns reordered subset of candidates.
    """
    if not candidates:
        return candidates

    # Prepare slim candidate list for the prompt (avoid token waste)
    slim = [
        {
            "url":             c["url"],
            "name":            c["name"],
            "description":     c["description"][:200],  # truncate long descs
            "test_types":      c["test_types"],
            "test_type_codes": c["test_type_codes"],
            "job_levels":      c["job_levels"],
            "duration":        c["duration"],
        }
        for c in candidates
    ]

    log.info("LLM reranking %d candidates via Groq ...", len(slim))
    t0 = time.time()
    try:
        response = groq.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0,
            max_tokens=500,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": reranking_prompt.format(
                        query=query,
                        candidates=json.dumps(slim, indent=2),
                    ),
                },
            ],
        )
        raw = response.choices[0].message.content.strip()
        log.info("LLM reranker response (%.2fs): %s", time.time() - t0, raw[:200])

        # Parse the returned URL list
        url_order = json.loads(raw)
        if not isinstance(url_order, list):
            raise ValueError("Expected JSON array of URLs")

        # Rebuild ordered results from candidate lookup
        by_url = {c["url"]: c for c in candidates}
        reranked = [by_url[url] for url in url_order if url in by_url]

        # Append any candidates the LLM didn't mention (safety fallback)
        seen = set(url_order)
        for c in candidates:
            if c["url"] not in seen:
                reranked.append(c)

        log.info("LLM reranker → %d ordered results", len(reranked))
        return reranked

    except Exception as e:
        log.warning("LLM reranker failed (%s) — falling back to RRF order", e)
        return candidates


# ── Duration filter ───────────────────────────────────────────────────────────

def extract_max_duration(query: str) -> int | None:
    """Parse max duration constraint from query text. Returns minutes or None."""
    q = query.lower()
    # Patterns: "40 minutes", "under 30 min", "max 60 minutes", "less than 45"
    m = re.search(r"(?:max(?:imum)?|under|less\s+than|within|up\s+to)?\s*(\d+)\s*(?:min(?:utes?)?|mins?)\b", q)
    if m:
        return int(m.group(1))
    # "1 hour" or "an hour"
    m = re.search(r"\b(\d+)\s*hour", q)
    if m:
        return int(m.group(1)) * 60
    if "an hour" in q or "one hour" in q:
        return 60
    return None



# ── Seniority detection & filtering ──────────────────────────────────────────

# job_levels 
JUNIOR_LEVELS  = {"Entry-Level", "Graduate"}
MID_LEVELS     = {"Mid-Professional", "Professional Individual Contributor", "General Population"}
MANAGER_LEVELS = {"Supervisor", "Front Line Manager", "Manager"}
SENIOR_LEVELS  = {"Director", "Executive"}

# (trigger phrases)  →  (acceptable levels for this query)
_SENIORITY_RULES: list[tuple[list[str], str]] = [
    # C-suite → senior only
    (["coo", "ceo", "cto", "cfo", "c-suite", "chief operating", "chief executive",
      "chief technology", "chief financial", "vice president", " vp ", "evp", "svp",
      "president and", "managing director"],
     "senior"),
    # Director
    (["director", "head of", "general manager"],
     "senior"),
    # Entry-level / graduate — most specific phrases first
    (["new graduate", "new graduates", "fresh graduate", "fresh graduates",
      "fresher", "entry level", "entry-level", "0-2 year", "0 to 2 year",
      "0 - 2 year", "0–2 year", "no experience", "0 years"],
     "junior"),
    # "graduate" alone (less specific)
    (["graduate"],
     "junior"),
    # Manager / supervisor
    (["manager", "team lead", "supervisor", "front line manager"],
     "manager"),
    # Mid / senior IC
    (["senior ", "sr. ", "lead ", "mid-level", "mid level"],
     "mid"),
]


def detect_seniority(query: str) -> str | None:
    """Return 'junior' | 'mid' | 'manager' | 'senior' | None."""
    q = " " + query.lower() + " "
    for phrases, tier in _SENIORITY_RULES:
        if any(p in q for p in phrases):
            log.info("Seniority detected: %s", tier)
            return tier
    return None


def seniority_score(candidate: dict, tier: str) -> float:
    """
    Score adjustment for seniority alignment.
    +1.0  = level matches perfectly
     0.0  = level-agnostic (empty job_levels) — always neutral
    -2.0  = clear opposite (Director tool for graduate, or Entry-Level tool for COO)
    -0.5  = partial mismatch
    """
    levels = set(candidate.get("job_levels", []))
    if not levels:          # level-agnostic tools like OPQ32r → neutral for all
        return 0.0

    if tier == "junior":
        if levels & JUNIOR_LEVELS:                     return  1.0
        if levels.issubset(SENIOR_LEVELS):             return -2.0   # Director-only for graduate
        return -0.5

    if tier == "senior":
        if levels & SENIOR_LEVELS:                     return  1.0
        if levels.issubset(JUNIOR_LEVELS):             return -2.0   # Entry-only for COO
        return -0.5

    if tier == "manager":
        if levels & MANAGER_LEVELS:                    return  1.0
        if levels.issubset(JUNIOR_LEVELS):             return -0.5
        return 0.0

    if tier == "mid":
        if levels & MID_LEVELS:                        return  1.0
        if levels & SENIOR_LEVELS and not (levels & MID_LEVELS): return -0.5
        return 0.0

    return 0.0

# ── Public entry point ────────────────────────────────────────────────────────

def recommend(query: str) -> list[dict]:
    log.info("=== recommend() called ===")
    log.info("Query: %.120s%s", query, "..." if len(query) > 120 else "")

    # Extract constraints from original query (before LLM expansion)
    max_duration = extract_max_duration(query)
    seniority    = detect_seniority(query)
    if max_duration:
        log.info("Duration constraint: ≤ %d minutes", max_duration)

    expanded   = expand_query(query)
    t0         = time.time()
    semantic   = semantic_search(expanded)
    keyword    = keyword_search(expanded)
    candidates = reciprocal_rank_fusion(semantic, keyword)
    log.info("Hybrid search done (%.2fs) — %d candidates", time.time() - t0, len(candidates))

    # ── Step 1: Duration hard filter ─────────────────────────────────────────
    if max_duration:
        before = len(candidates)
        candidates = [
            c for c in candidates
            if c.get("duration") is None or c["duration"] <= max_duration
        ]
        log.info("Duration filter (≤%d min): %d → %d", max_duration, before, len(candidates))

    # ── Step 2: Seniority hard-exclude ───────────────────────────────────────
    # Remove assessments whose ENTIRE job_levels list is in the wrong extreme.
    # e.g. a Director/Executive-only tool should never appear for a graduate query.
    # Level-agnostic assessments (empty job_levels) are always kept.
    if seniority:
        # Acceptable levels per seniority tier — keep if levels overlap with these
        ACCEPT_FOR = {
            "junior": JUNIOR_LEVELS | MID_LEVELS,  # Entry-Level, Graduate, General Population, Mid-Pro, IC
            "senior": SENIOR_LEVELS | MANAGER_LEVELS,  # Director, Executive, Manager, FLM, Supervisor
        }
        accept = ACCEPT_FOR.get(seniority, set())
        if accept:
            before = len(candidates)
            hard_filtered = [
                c for c in candidates
                if not c.get("job_levels")              # level-agnostic → always keep
                or bool(set(c["job_levels"]) & accept)  # has at least one acceptable level → keep
            ]
            if len(hard_filtered) >= 5:
                candidates = hard_filtered
                log.info("Seniority hard-exclude (%s): %d → %d", seniority, before, len(candidates))
            else:
                log.warning("Seniority hard-exclude would leave %d — skipping", len(hard_filtered))

    # ── Step 3: Seniority re-rank (soft boost/penalty on remaining) ──────────
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