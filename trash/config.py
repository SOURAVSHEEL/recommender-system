import logging
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler()],
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("faiss").setLevel(logging.WARNING)

# Paths
STORE_PATH  = BASE_DIR / "embeddings" / "faiss_store"
PROMPTS_DIR = BASE_DIR / "prompts"

OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")  

# Groq (query expansion + reranking)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY not found.\n"
        f"Add it to: {BASE_DIR / '.env'}"
    )

# ── Retrieval tuning ──────────────────────────────────────────────────────────

TOP_K_SEMANTIC = int(os.getenv("TOP_K_SEMANTIC", "20"))
TOP_K_KEYWORD  = int(os.getenv("TOP_K_KEYWORD",  "20"))   
TOP_K_RERANK   = int(os.getenv("TOP_K_RERANK",   "25"))  
TOP_K_FINAL    = int(os.getenv("TOP_K_FINAL",    "10"))

# ── RRF tuning ────────────────────────────────────────────────────────────────
RRF_K = int(os.getenv("RRF_K", "10"))                   