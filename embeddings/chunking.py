import json
import re
import uuid
import os
import time
from pathlib import Path

CATALOG_PATH    = Path("scraper/catalog.json")
STORE_PATH      = Path("embeddings/catalog_chunks.json")

# ── Load source data ──────────────────────────────────────────────────────────
print(f"Loading catalog from {CATALOG_PATH} ...")
with open(CATALOG_PATH, "r", encoding="utf-8") as f:
    catalog = json.load(f)
print(f"  {len(catalog)} assessments loaded.")



# ── Helper: create a clean slug from the item name ───────────────────────────
def make_chunk_key(name: str) -> str:
    key = name.lower()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = key.strip("_")
    return key


# ── Build chunks: one dict per catalog item ───────────────────────────────────
chunks = []
seen_keys = set()

for idx, item in enumerate(catalog):
    chunk_key = make_chunk_key(item["name"])

    if chunk_key in seen_keys:
        chunk_key = f"{chunk_key}_{idx}"
    seen_keys.add(chunk_key)

    chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_key))

    chunks.append({
        "chunk_id":        chunk_id,
        "chunk_key":       chunk_key,
        "name":            item.get("name"),
        "url":             item.get("url"),
        "description":     item.get("description"),
        "job_levels":      item.get("job_levels", []),
        "languages":       item.get("languages", []),
        "duration":        item.get("duration"),
        "remote_testing":  item.get("remote_testing"),
        "adaptive":        item.get("adaptive"),
        "test_type_codes": item.get("test_type_codes", []),
        "test_types":      item.get("test_types", []),
        "search_text":     item.get("search_text"),
    })

# ── Save output ───────────────────────────────────────────────────────────────

with open(STORE_PATH, "w", encoding="utf-8") as f:
    json.dump(chunks, f, indent=2, ensure_ascii=False)

print(f"✅  {len(chunks)} chunks written → {STORE_PATH}")
print("\n── PREVIEW (first 2 chunks) ──")
print(json.dumps(chunks[:2], indent=2))