# """
# recommender.py — core RAG pipeline

# Flow:
#   1. Load prompt templates from prompts/*.md
#   2. Expand query via Groq LLM (mixtral-8x7b-32768)
#   3. Retrieve top-K candidates from FAISS using Ollama embeddings
#   4. Re-rank via Groq LLM using reranking prompt
#   5. Return ordered list of Assessment dicts
# """

# import json
# import re

# from langchain_community.vectorstores import FAISS
# from langchain_ollama import OllamaEmbeddings
# from langchain_groq import ChatGroq

# from api.config import (
#     STORE_PATH, PROMPTS_DIR,
#     OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL,
#     GROQ_API_KEY, GROQ_MODEL,
#     TOP_K_RETRIEVE, TOP_K_FINAL,
# )


# # ── Load prompt templates once at import time ─────────────────────────────────

# def _load_prompt(name: str) -> str:
#     return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")

# QUERY_EXPANSION_TMPL = _load_prompt("query_expansion")
# RERANKING_TMPL       = _load_prompt("reranking")


# # ── Lazy singletons ───────────────────────────────────────────────────────────

# _vector_store = None
# _llm          = None


# def _get_vector_store() -> FAISS:
#     global _vector_store
#     if _vector_store is None:
#         embeddings = OllamaEmbeddings(
#             model=OLLAMA_EMBED_MODEL,
#             base_url=OLLAMA_BASE_URL,
#         )
#         _vector_store = FAISS.load_local(
#             str(STORE_PATH),
#             embeddings,
#             allow_dangerous_deserialization=True,
#         )
#     return _vector_store


# def _get_llm() -> ChatGroq:
#     global _llm
#     if _llm is None:
#         _llm = ChatGroq(
#             temperature=0,
#             model_name=GROQ_MODEL,
#             groq_api_key=GROQ_API_KEY,
#         )
#     return _llm


# # ── Pipeline steps ────────────────────────────────────────────────────────────

# def _expand_query(query: str) -> str:
#     """Use Groq LLM to enrich terse queries with related skills and competencies."""
#     prompt = QUERY_EXPANSION_TMPL.format(query=query)
#     expanded = _get_llm().invoke(prompt).content.strip()
#     return f"{query}\n{expanded}"


# def _retrieve(expanded_query: str) -> list[dict]:
#     """Embed expanded query and fetch top-K candidates from FAISS."""
#     docs = _get_vector_store().similarity_search(expanded_query, k=TOP_K_RETRIEVE)
#     return [doc.metadata for doc in docs]


# def _rerank(query: str, candidates: list[dict]) -> list[str]:
#     """
#     Ask Groq LLM to select and order the most relevant assessment URLs.
#     Returns an ordered list of URLs (5–10 items).
#     """
#     candidates_json = json.dumps(
#         [
#             {
#                 "url":             c["url"],
#                 "name":            c["name"],
#                 "test_type_codes": c["test_type_codes"],
#                 "description":     c["description"][:200],
#             }
#             for c in candidates
#         ],
#         indent=2,
#     )
#     prompt = RERANKING_TMPL.format(query=query, candidates=candidates_json)
#     response = _get_llm().invoke(prompt).content.strip()

#     # Strip markdown fences if LLM wraps output in ```json ... ```
#     response = re.sub(r"```(?:json)?|```", "", response).strip()
#     urls = json.loads(response)
#     return urls[:TOP_K_FINAL]


# # ── Public entry point ────────────────────────────────────────────────────────

# def recommend(query: str) -> list[dict]:
#     """Full RAG pipeline. Returns list of assessment dicts ready for API response."""
#     expanded    = _expand_query(query)
#     candidates  = _retrieve(expanded)
#     lookup      = {c["url"]: c for c in candidates}
#     ranked_urls = _rerank(query, candidates)

#     results = []
#     for url in ranked_urls:
#         meta = lookup.get(url)
#         if not meta:
#             continue
#         results.append({
#             "name":             meta["name"],
#             "url":              meta["url"],
#             "description":      meta["description"],
#             "duration":         meta["duration"],
#             "remote_support":   "Yes" if meta["remote_testing"] else "No",
#             "adaptive_support": "Yes" if meta["adaptive"] else "No",
#             "test_type":        meta["test_types"],
#         })

#     return results


"""
recommender.py — core RAG pipeline (Gemini Version)

Flow:
  1. Load prompt templates from prompts/*.md
  2. Expand query via Gemini LLM
  3. Retrieve top-K candidates from FAISS using Ollama embeddings
  4. Re-rank via Gemini using reranking prompt
  5. Return ordered list of Assessment dicts
"""

import json
import re
import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings

from api.config import (
    STORE_PATH, PROMPTS_DIR,
    OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL,
    TOP_K_RETRIEVE, TOP_K_FINAL,
)

# ── Configure Gemini Client ──────────────────────────────────────────────────

# client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# model = ChatGoogleGenerativeAI(model="gemini-3.1-pro-preview", api_key=)

GEMINI_MODEL = "gemini-3-flash-preview"
model = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0
)
# ── Load prompt templates once at import time ────────────────────────────────

def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")

QUERY_EXPANSION_TMPL = load_prompt("query_expansion")
RERANKING_TMPL       = load_prompt("reranking")

# ── Lazy vector store singleton ──────────────────────────────────────────────

vector_store = None

def get_vector_store() -> FAISS:
    global vector_store
    if vector_store is None:
        embeddings = OllamaEmbeddings(
            model=OLLAMA_EMBED_MODEL,
            base_url=OLLAMA_BASE_URL,
        )
        vector_store = FAISS.load_local(
            str(STORE_PATH),
            embeddings,
            allow_dangerous_deserialization=True,
        )
    return vector_store

# ── Gemini Helper ────────────────────────────────────────────────────────────

def call_gemini(prompt: str) -> str:
    response = model.invoke(prompt)
    return response.content.strip()

# ── Pipeline steps ────────────────────────────────────────────────────────────

def expand_query(query: str) -> str:
    """Use Gemini to enrich terse queries."""
    prompt = QUERY_EXPANSION_TMPL.format(query=query)
    expanded = call_gemini(prompt)
    return f"{query}\n{expanded}"

def retrieve(expanded_query: str) -> list[dict]:
    """Embed expanded query and fetch top-K candidates from FAISS."""
    docs = get_vector_store().similarity_search(expanded_query, k=TOP_K_RETRIEVE)
    return [doc.metadata for doc in docs]

def rerank(query: str, candidates: list[dict]) -> list[str]:
    """
    Ask Gemini to select and order the most relevant assessment URLs.
    Returns ordered list of URLs.
    """
    candidates_json = json.dumps(
        [
            {
                "url":             c["url"],
                "name":            c["name"],
                "test_type_codes": c["test_type_codes"],
                "description":     c["description"][:200],
            }
            for c in candidates
        ],
        indent=2,
    )

    prompt = RERANKING_TMPL.format(query=query, candidates=candidates_json)

    response = call_gemini(prompt)

    # Remove markdown fences if present
    response = re.sub(r"```(?:json)?|```", "", response).strip()

    urls = json.loads(response)
    return urls[:TOP_K_FINAL]

# ── Public entry point ────────────────────────────────────────────────────────

def recommend(query: str) -> list[dict]:
    """Full RAG pipeline. Returns list of assessment dicts ready for API response."""
    expanded    = expand_query(query)
    candidates  = retrieve(expanded)
    lookup      = {c["url"]: c for c in candidates}
    ranked_urls = rerank(query, candidates)

    results = []
    for url in ranked_urls:
        meta = lookup.get(url)
        if not meta:
            continue
        results.append({
            "name":             meta["name"],
            "url":              meta["url"],
            "description":      meta["description"],
            "duration":         meta["duration"],
            "remote_support":   "Yes" if meta["remote_testing"] else "No",
            "adaptive_support": "Yes" if meta["adaptive"] else "No",
            "test_type":        meta["test_types"],
        })

    return results