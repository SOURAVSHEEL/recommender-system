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

# Google Generative AI (embeddings)
GOOGLE_API_KEY    = os.getenv("GOOGLE_API_KEY")
GOOGLE_EMBED_MODEL = os.getenv("GOOGLE_EMBED_MODEL", "models/gemini-embedding-001")

if not GOOGLE_API_KEY:
    raise ValueError(
        "GOOGLE_API_KEY not found.\n"
        f"Add it to: {BASE_DIR / '.env'}"
    )

# Second API key — used exclusively for query expansion
# Falls back to GOOGLE_API_KEY if not set
GOOGLE_API_KEY_2 = os.getenv("GOOGLE_API_KEY_2") or GOOGLE_API_KEY

# Gemini (query expansion + reranking) — Gemini 2.5 Flash
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ── Retrieval tuning ──────────────────────────────────────────────────────────

TOP_K_SEMANTIC = int(os.getenv("TOP_K_SEMANTIC", "20"))
TOP_K_KEYWORD  = int(os.getenv("TOP_K_KEYWORD",  "20"))   
TOP_K_RERANK   = int(os.getenv("TOP_K_RERANK",   "25"))  
TOP_K_FINAL    = int(os.getenv("TOP_K_FINAL",    "10"))

# ── RRF tuning ────────────────────────────────────────────────────────────────
RRF_K = int(os.getenv("RRF_K", "10"))