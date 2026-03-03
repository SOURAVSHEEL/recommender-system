import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings
from langchain.docstore.document import Document

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
CATALOG_PATH    = Path("scraper/catalog.json")
STORE_PATH      = Path("embeddings/faiss_store")


def build_index():
    # ── Load catalog ──────────────────────────────────────────────────────────
    print(f"Loading catalog from {CATALOG_PATH} ...")
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    print(f"  {len(catalog)} assessments loaded.")

    # ── Build LangChain Documents ─────────────────────────────────────────────
    docs = [
        Document(
            page_content=rec["search_text"],
            metadata={
                "name":            rec["name"],
                "url":             rec["url"],
                "description":     rec["description"],
                "duration":        rec["duration"],
                "remote_testing":  rec["remote_testing"],
                "adaptive":        rec["adaptive"],
                "test_type_codes": rec["test_type_codes"],
                "test_types":      rec["test_types"],
            },
        )
        for rec in catalog
    ]
    print(f"  {len(docs)} Documents created.")

    # ── Ollama Embeddings ─────────────────────────────────────────────────────
    print(f"\nInitialising Ollama embedding model: {OLLAMA_MODEL} ...")
    print(f"  Ollama base URL: {OLLAMA_BASE_URL}")
    embeddings = OllamaEmbeddings(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
    )

    # ── Build & save FAISS vector store ───────────────────────────────────────
    print("Building FAISS vector store ...")
    t0 = time.time()
    vector_store = FAISS.from_documents(docs, embeddings)
    print(f"  Done in {time.time() - t0:.1f}s — {vector_store.index.ntotal} vectors indexed.")

    STORE_PATH.mkdir(parents=True, exist_ok=True)
    vector_store.save_local(str(STORE_PATH))
    print(f"  Store saved → {STORE_PATH}/")

    print("\n✓ FAISS index ready. Next step: python api/main.py\n")


if __name__ == "__main__":
    build_index()