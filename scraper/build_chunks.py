import json
import logging
import re
import uuid
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

INPUT_PATH  = Path(__file__).parent / "catalog.json"
OUTPUT_PATH = Path(__file__).parent / "catalog_chunks.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slug_from_url(url: str) -> str:
    """Extract URL slug: last path segment, stripped of trailing slash."""
    return url.rstrip("/").split("/")[-1].lower()


def _chunk_key(slug: str) -> str:
    """Convert URL slug to snake_case chunk key.
    e.g. 'core-java-entry-level-new' → 'core_java_entry_level_new'
    """
    key = re.sub(r"[^a-z0-9]+", "_", slug.lower())
    return key.strip("_")


def _stable_uuid(slug: str) -> str:
    """Generate a deterministic UUID from the slug (UUID5, DNS namespace).
    Same slug always produces the same chunk_id — safe to re-run.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"shl.com/{slug}"))


def _build_search_text(rec: dict) -> str:
    """
    Rich natural-language string for embedding.
    Structured to give nomic-embed-text maximum semantic signal:
      - Name first (highest weight)
      - Description in full
      - Explicit labels for test types and job levels
      - Duration and capabilities
    """
    parts = []

    name = rec.get("name", "").strip()
    if name:
        parts.append(name + ".")

    desc = rec.get("description", "").strip()
    if desc:
        parts.append(desc)

    types = rec.get("test_types", [])
    if types:
        parts.append("Assessment type: " + ", ".join(types) + ".")

    codes = rec.get("test_type_codes", [])
    if codes:
        parts.append("Type codes: " + " ".join(codes) + ".")

    levels = rec.get("job_levels", [])
    if levels:
        parts.append("Suitable job levels: " + ", ".join(levels) + ".")

    langs = rec.get("languages", [])
    if langs:
        parts.append("Available in: " + ", ".join(langs[:5]) + ".")

    dur = rec.get("duration")
    if dur is not None:
        parts.append(f"Duration: {dur} minutes.")

    remote   = "Yes" if rec.get("remote_testing") else "No"
    adaptive = "Yes" if rec.get("adaptive") else "No"
    parts.append(f"Remote testing: {remote}. Adaptive/IRT: {adaptive}.")

    return " ".join(parts)


# ── Main ──────────────────────────────────────────────────────────────────────

def build_chunks(
    input_path: Path = INPUT_PATH,
    output_path: Path = OUTPUT_PATH,
) -> list[dict]:

    log.info("Loading catalog from: %s", input_path)
    with open(input_path, encoding="utf-8") as f:
        catalog = json.load(f)
    log.info("Loaded %d records.", len(catalog))

    chunks = []
    seen_keys: set[str] = set()
    skipped = 0

    for rec in catalog:
        url  = rec.get("url", "").strip()
        name = rec.get("name", "").strip()

        if not url or not name:
            log.warning("Skipping record with missing url or name: %s", rec)
            skipped += 1
            continue

        slug  = _slug_from_url(url)
        key   = _chunk_key(slug)
        cid   = _stable_uuid(slug)

        # Deduplicate by chunk_key
        if key in seen_keys:
            log.debug("Duplicate chunk_key '%s' — skipping.", key)
            skipped += 1
            continue
        seen_keys.add(key)

        search_text = _build_search_text(rec)

        chunk = {
            # ── Chunk identity ────────────────────────────────────────────────
            "chunk_id":  cid,
            "chunk_key": key,

            # ── Embedding field ───────────────────────────────────────────────
            "search_text": search_text,

            # ── Metadata (stored in FAISS docstore → index.pkl) ───────────────
            # Response building
            "name":        name,
            "url":         url,
            "description": rec.get("description", "").strip(),

            # BM25 keyword search fields
            "job_levels":      rec.get("job_levels", []),
            "test_types":      rec.get("test_types", []),
            "test_type_codes": rec.get("test_type_codes", []),
            "languages":       rec.get("languages", []),

            # Hard filter field
            "duration": rec.get("duration"),   # int minutes or None

            # Feature flags
            "remote_testing": bool(rec.get("remote_testing", False)),
            "adaptive":       bool(rec.get("adaptive", False)),
        }
        chunks.append(chunk)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    log.info("Built %d chunks → %s  (skipped %d)", len(chunks), output_path, skipped)

    # Quick stats
    with_duration = sum(1 for c in chunks if c["duration"] is not None)
    with_levels   = sum(1 for c in chunks if c["job_levels"])
    remote_count  = sum(1 for c in chunks if c["remote_testing"])
    log.info(
        "Stats — with_duration: %d  with_job_levels: %d  remote_testing: %d",
        with_duration, with_levels, remote_count,
    )

    return chunks


if __name__ == "__main__":
    chunks = build_chunks()

    # Print 2 sample chunks for visual verification
    print("\n── Sample chunks ──────────────────────────────────────────")
    for c in chunks[:2]:
        print(json.dumps(c, indent=2))
        print()