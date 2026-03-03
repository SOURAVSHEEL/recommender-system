"""
recommender.py — core RAG pipeline

Flow:
  1. Expand query via Groq LLM
  2. Retrieve top-K candidates from FAISS using Ollama embeddings
  3. Return results directly (no re-ranking)
"""

from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings
from langchain_groq import ChatGroq

from api.config import (
    STORE_PATH, PROMPTS_DIR,
    OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL,
    GROQ_API_KEY, GROQ_MODEL,
    TOP_K_FINAL,
)


# ── Load prompt template ──────────────────────────────────────────────────────

QUERY_EXPANSION_TMPL = (PROMPTS_DIR / "query_expansion.md").read_text(encoding="utf-8")


# ── Lazy singletons ───────────────────────────────────────────────────────────

_vector_store = None
_llm          = None


def _get_vector_store() -> FAISS:
    global _vector_store
    if _vector_store is None:
        embeddings = OllamaEmbeddings(
            model=OLLAMA_EMBED_MODEL,
            base_url=OLLAMA_BASE_URL,
        )
        _vector_store = FAISS.load_local(
            str(STORE_PATH),
            embeddings,
            allow_dangerous_deserialization=True,
        )
    return _vector_store


def _get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            temperature=0,
            model_name=GROQ_MODEL,
            groq_api_key=GROQ_API_KEY,
        )
    return _llm


# ── Pipeline steps ────────────────────────────────────────────────────────────

def _expand_query(query: str) -> str:
    prompt = QUERY_EXPANSION_TMPL.format(query=query)
    expanded = _get_llm().invoke(prompt).content.strip()
    return f"{query}\n{expanded}"


def _retrieve(expanded_query: str) -> list[dict]:
    docs = _get_vector_store().similarity_search(expanded_query, k=TOP_K_FINAL)
    return [doc.metadata for doc in docs]


# ── Public entry point ────────────────────────────────────────────────────────

def recommend(query: str) -> list[dict]:
    expanded   = _expand_query(query)
    candidates = _retrieve(expanded)

    return [
        {
            "name":             c["name"],
            "url":              c["url"],
            "description":      c["description"],
            "duration":         c["duration"],
            "remote_support":   "Yes" if c["remote_testing"] else "No",
            "adaptive_support": "Yes" if c["adaptive"] else "No",
            "test_type":        c["test_types"],
        }
        for c in candidates
    ]