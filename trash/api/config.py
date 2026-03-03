"""
config.py — centralised settings loaded from .env
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR    = Path(__file__).resolve().parent.parent
STORE_PATH  = BASE_DIR / "embeddings" / "faiss_store"
PROMPTS_DIR = BASE_DIR / "prompts"

# Ollama (embeddings only)
OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# Groq LLM
GROQ_API_KEY  = os.getenv("GROQ_API_KEY")
GROQ_MODEL    = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")



if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY not found.\n"
        f"Make sure your .env file exists at: {BASE_DIR / '.env'}\n"
        "and contains: GROQ_API_KEY=your-key-here"
    )

# Retrieval
TOP_K_RETRIEVE = int(os.getenv("TOP_K_RETRIEVE", "20"))
TOP_K_FINAL    = int(os.getenv("TOP_K_FINAL", "10"))