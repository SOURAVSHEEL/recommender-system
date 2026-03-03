"""
recommender.py — Core RAG pipeline

Pipeline:
  1. Query expansion via Groq → rich semantic paragraph (for FAISS only)
  2. Keyword distillation via Groq → short keyword phrase (for BM25 only)
  3. Hybrid search — semantic (FAISS on expanded) + keyword (BM25 on distilled)
  4. Reciprocal Rank Fusion with tuned k
  5. Duration hard filter
  6. LLM reranker via Groq (reranking.md) — selects & orders final results
  7. Return top-K diverse results

Key fixes vs original:
  - FIX 1: Embedding model aligned (nomic-embed-text, matches build_index)
  - FIX 2: BM25 corpus now includes description (rich skill keywords)
  - FIX 3: Separate query forms: expanded paragraph → FAISS, keyword phrase → BM25
  - FIX 4: RRF k lowered from 60 → 10 for better rank differentiation
  - FIX 5: LLM reranker now actually wired up (reranking.md was dead code)
  - FIX 6: Reranker enforces test_type diversity (K + P balance)
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
    RRF_K,
)

log = logging.getLogger(__name__)

# ── Prompts ───────────────────────────────────────────────────────────────────

_system_prompt    = (PROMPTS_DIR / "system.md").read_text(encoding="utf-8").strip()
_expansion_prompt = (PROMPTS_DIR / "query_expansion.md").read_text(encoding="utf-8").strip()
_reranking_prompt = (PROMPTS_DIR / "reranking.md").read_text(encoding="utf-8").strip()

# ── Groq client ───────────────────────────────────────────────────────────────

_groq = Groq(api_key=GROQ_API_KEY)

# ── Stopwords ─────────────────────────────────────────────────────────────────

_STOPWORDS = {
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


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric, remove stopwords and short tokens."""
    tokens = re.split(r"[^a-z0-9\.#\+]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


# ── Query expansion — two forms ───────────────────────────────────────────────

# FIX 3: BM25 and FAISS need different query representations.
# FAISS (semantic): benefits from a rich, context-heavy paragraph.
# BM25 (keyword):   benefits from a short, precise keyword phrase — no filler words.

_KEYWORD_DISTILL_PROMPT = """\
Given the job query below, extract a concise keyword phrase (10-20 words max) \
capturing only the core role, skills, and technologies. No full sentences. \
No filler words. Think of it as a search engine query.

Return ONLY the keyword phrase.

Query: {query}"""


def _expand_query(query: str) -> tuple[str, str]:
    """
    Returns (expanded_paragraph, keyword_phrase).
    expanded_paragraph → fed to FAISS semantic search
    keyword_phrase     → fed to BM25 keyword search
    """
    log.info("Expanding query via Groq (%s) ...", GROQ_MODEL)
    t0 = time.time()

    # Call 1: rich semantic expansion for FAISS
    r1 = _groq.chat.completions.create(
        model=GROQ_MODEL,
        temperature=0,
        max_tokens=300,
        messages=[
            {"role": "system", "content": _system_prompt},
            {"role": "user",   "content": _expansion_prompt.format(query=query)},
        ],
    )
    expanded = r1.choices[0].message.content.strip()

    # Call 2: keyword distillation for BM25
    r2 = _groq.chat.completions.create(
        model=GROQ_MODEL,
        temperature=0,
        max_tokens=60,
        messages=[
            {"role": "user", "content": _KEYWORD_DISTILL_PROMPT.format(query=query)},
        ],
    )
    keywords = r2.choices[0].message.content.strip()

    log.info(
        "Query forms ready (%.2fs)\n  Semantic: %s\n  Keywords: %s",
        time.time() - t0, expanded[:100], keywords,
    )
    return expanded, keywords


# ── Lazy singletons ───────────────────────────────────────────────────────────

_vector_store : FAISS | None     = None
_bm25         : BM25Okapi | None = None
_bm25_metadata: list[dict]       = []


def _get_vector_store() -> FAISS:
    global _vector_store
    if _vector_store is None:
        log.info("Loading FAISS vector store from: %s", STORE_PATH)
        t0 = time.time()
        embeddings = OllamaEmbeddings(model=OLLAMA_EMBED_MODEL, base_url=OLLAMA_BASE_URL)
        _vector_store = FAISS.load_local(
            str(STORE_PATH), embeddings, allow_dangerous_deserialization=True
        )
        log.info("FAISS store loaded — %d vectors (%.2fs)", _vector_store.index.ntotal, time.time() - t0)
    return _vector_store


def _get_bm25() -> tuple[BM25Okapi, list[dict]]:
    global _bm25, _bm25_metadata
    if _bm25 is None:
        log.info("Building BM25 index ...")
        t0 = time.time()
        docs = list(_get_vector_store().docstore._dict.values())
        _bm25_metadata = [doc.metadata for doc in docs]

        # FIX 2: BM25 corpus now includes description.
        # Original only used name + job_levels + test_types, which meant all the
        # rich skill keywords in descriptions (Python, SQL, security, etc.) were
        # completely invisible to keyword search. Description is the most
        # information-dense field for skill matching.
        corpus = [
            _tokenize(
                doc.metadata.get("name", "") + " "
                + doc.metadata.get("description", "") + " "        # ← ADDED
                + " ".join(doc.metadata.get("job_levels", [])) + " "
                + " ".join(doc.metadata.get("test_types", []))
            )
            for doc in docs
        ]
        _bm25 = BM25Okapi(corpus)
        log.info("BM25 index built — %d docs (%.2fs)", len(corpus), time.time() - t0)
    return _bm25, _bm25_metadata


# ── Search ────────────────────────────────────────────────────────────────────

def _semantic_search(expanded_query: str) -> list[tuple[dict, int]]:
    """FAISS search using the rich semantic paragraph."""
    docs = _get_vector_store().similarity_search(expanded_query, k=TOP_K_SEMANTIC)
    log.info("Semantic search → %d results", len(docs))
    return [(doc.metadata, rank) for rank, doc in enumerate(docs)]


def _keyword_search(keyword_query: str) -> list[tuple[dict, int]]:
    """BM25 search using the short keyword phrase."""
    bm25, metadata = _get_bm25()
    scores  = bm25.get_scores(_tokenize(keyword_query))
    top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:TOP_K_KEYWORD]
    log.info("BM25 search → %d results", len(top_idx))
    return [(metadata[i], rank) for rank, i in enumerate(top_idx)]


def _reciprocal_rank_fusion(
    semantic: list[tuple[dict, int]],
    keyword:  list[tuple[dict, int]],
) -> list[dict]:
    # FIX 4: Use RRF_K from config (default 10) instead of hardcoded 60.
    # k=60 was designed for corpora of thousands of docs. With 377 docs and
    # TOP_K=20, the score spread at k=60 is negligible (0.0164 vs 0.0123).
    # k=10 gives much sharper differentiation: 1/11=0.091 vs 1/31=0.032.
    scores: dict[str, float] = {}
    by_url: dict[str, dict]  = {}

    for meta, rank in semantic:
        url = meta["url"]
        scores[url] = scores.get(url, 0) + 1 / (RRF_K + rank + 1)
        by_url[url] = meta

    for meta, rank in keyword:
        url = meta["url"]
        scores[url] = scores.get(url, 0) + 1 / (RRF_K + rank + 1)
        by_url[url] = meta

    ranked = sorted(scores, key=lambda u: scores[u], reverse=True)
    log.info(
        "RRF (k=%d) — semantic: %d, keyword: %d → %d unique candidates",
        RRF_K, len(semantic), len(keyword), len(ranked),
    )
    return [by_url[url] for url in ranked]


# ── LLM Reranker ─────────────────────────────────────────────────────────────

def _llm_rerank(query: str, candidates: list[dict]) -> list[dict]:
    """
    FIX 5: Actually use reranking.md.
    Send top candidates to Groq for LLM-based relevance reranking.
    The prompt also enforces K+P type diversity (FIX 6).
    Returns reordered subset of candidates.
    """
    if not candidates:
        return candidates

    # Prepare slim candidate list for the prompt (avoid token waste)
    slim = [
        {
            "url":         c["url"],
            "name":        c["name"],
            "description": c["description"][:200],  # truncate long descs
            "test_types":  c["test_types"],
            "test_type_codes": c["test_type_codes"],
            "job_levels":  c["job_levels"],
            "duration":    c["duration"],
        }
        for c in candidates
    ]

    log.info("LLM reranking %d candidates via Groq ...", len(slim))
    t0 = time.time()
    try:
        response = _groq.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0,
            max_tokens=500,
            messages=[
                {"role": "system", "content": _system_prompt},
                {
                    "role": "user",
                    "content": _reranking_prompt.format(
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

def _extract_max_duration(query: str) -> int | None:
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


# ── Public entry point ────────────────────────────────────────────────────────

def recommend(query: str) -> list[dict]:
    log.info("=== recommend() called ===")
    log.info("Query: %.120s%s", query, "..." if len(query) > 120 else "")

    # Extract duration constraint from original query (before expansion)
    max_duration = _extract_max_duration(query)
    if max_duration:
        log.info("Duration constraint detected: ≤ %d minutes", max_duration)

    # Step 1: Generate two query forms
    expanded, keywords = _expand_query(query)

    # Step 2: Hybrid search — each arm uses the right query form
    t0       = time.time()
    semantic = _semantic_search(expanded)   # rich paragraph → FAISS
    keyword  = _keyword_search(keywords)    # short keywords → BM25
    candidates = _reciprocal_rank_fusion(semantic, keyword)
    log.info("Hybrid search done (%.2fs) — %d candidates", time.time() - t0, len(candidates))

    # Step 3: Duration hard filter (applied before reranking to reduce LLM input)
    if max_duration:
        before = len(candidates)
        candidates = [
            c for c in candidates
            if c.get("duration") is None or c["duration"] <= max_duration
        ]
        log.info("Duration filter (≤%d min): %d → %d candidates", max_duration, before, len(candidates))

    # Step 4: LLM reranking on top candidates
    rerank_pool = candidates[:TOP_K_RERANK]
    reranked    = _llm_rerank(query, rerank_pool)

    # Step 5: Build final response
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