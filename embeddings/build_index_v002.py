import json
import logging
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings
from langchain.docstore.document import Document
import os

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

CHUNKS_PATH        = Path("scraper/catalog_chunks.json")
STORE_PATH         = Path("embeddings/faiss_store")
OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")


def build_index():
    # ── Load chunks ───────────────────────────────────────────────────────────
    log.info("Loading chunks from: %s", CHUNKS_PATH)
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = json.load(f)
    log.info("Loaded %d chunks.", len(chunks))

    # ── Build LangChain Documents ─────────────────────────────────────────────
    # page_content → embedded (semantic search)
    # metadata     → stored in docstore (BM25 + duration filter + response)
    docs = [
        Document(
            page_content=chunk["search_text"],
            metadata={
                "chunk_id":        chunk["chunk_id"],
                "chunk_key":       chunk["chunk_key"],
                "name":            chunk["name"],
                "url":             chunk["url"],
                "description":     chunk["description"],
                "job_levels":      chunk["job_levels"],
                "test_types":      chunk["test_types"],
                "test_type_codes": chunk["test_type_codes"],
                "languages":       chunk["languages"],
                "duration":        chunk["duration"],
                "remote_testing":  chunk["remote_testing"],
                "adaptive":        chunk["adaptive"],
            },
        )
        for chunk in chunks
    ]
    log.info("Built %d Documents.", len(docs))

    # ── Embed ─────────────────────────────────────────────────────────────────
    log.info("Initialising embedding model: %s @ %s", OLLAMA_EMBED_MODEL, OLLAMA_BASE_URL)
    embeddings = OllamaEmbeddings(
        model=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )

    log.info("Building FAISS vector store ...")
    t0 = time.time()
    vector_store = FAISS.from_documents(docs, embeddings)
    log.info(
        "FAISS store built — %d vectors, dim=%d (%.1fs)",
        vector_store.index.ntotal,
        vector_store.index.d,
        time.time() - t0,
    )

    # ── Save ──────────────────────────────────────────────────────────────────
    STORE_PATH.mkdir(parents=True, exist_ok=True)
    vector_store.save_local(str(STORE_PATH))
    log.info("Saved → %s/  (index.faiss + index.pkl)", STORE_PATH)

    log.info("✓ Index ready. Run: uvicorn api.main:app --reload --port 8000")


if __name__ == "__main__":
    build_index()


