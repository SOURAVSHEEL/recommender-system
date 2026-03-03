import json
import logging
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
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
GOOGLE_API_KEY     = os.getenv("GOOGLE_API_KEY")
GOOGLE_EMBED_MODEL = os.getenv("GOOGLE_EMBED_MODEL", "models/gemini-embedding-001")


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
    log.info("Initialising embedding model: %s", GOOGLE_EMBED_MODEL)
    embeddings = GoogleGenerativeAIEmbeddings(
        model=GOOGLE_EMBED_MODEL,
        google_api_key=GOOGLE_API_KEY,
        task_type="retrieval_document",
    )

    log.info("Building FAISS vector store (batched) ...")
    t0 = time.time()

    # Free tier: 100 requests/min. Each doc = 1 request.
    # 50 docs/batch + 65s sleep → ~46 docs/min
    BATCH_SIZE = 50
    SLEEP_SECS = 65
    MAX_RETRIES = 3
    vector_store = None

    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i:i + BATCH_SIZE]
        log.info("Embedding batch %d → %d / %d", i, i + len(batch), len(docs))

        # Auto-retry on 429 quota errors
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if vector_store is None:
                    vector_store = FAISS.from_documents(batch, embeddings)
                else:
                    vector_store.add_documents(batch)
                break  # success — exit retry loop
            except Exception as e:
                if "429" in str(e) or "ResourceExhausted" in type(e).__name__:
                    wait = 60 * attempt  # 60s, 120s, 180s
                    log.warning("Quota hit (attempt %d/%d) — retrying in %ds ...", attempt, MAX_RETRIES, wait)
                    time.sleep(wait)
                else:
                    raise  # non-quota error 
        else:
            raise RuntimeError(f"Batch {i}–{i+len(batch)} failed after {MAX_RETRIES} retries.")

        # Sleep between batches (skip after last batch)
        if i + BATCH_SIZE < len(docs):
            log.info("Sleeping %ds to respect free-tier quota ...", SLEEP_SECS)
            time.sleep(SLEEP_SECS)

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



if __name__ == "__main__":
    build_index()