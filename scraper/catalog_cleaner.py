"""
catalog_cleaner.py
==================
Post-processes catalog_raw.json produced by shl_scraper.py.

Operations performed:
  1. Deduplicate by URL (keep first occurrence).
  2. Strip & normalize all string fields.
  3. Standardise duration — coerce to int or None.
  4. Validate required fields; log any records that are incomplete.
  5. Build a rich `search_text` field used for embedding downstream.
  6. Validate final count ≥ 377 and emit a clear pass/fail message.

Output: scraper/catalog.json
"""

import json
import logging
import re
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

INPUT_PATH  = Path(__file__).parent / "catalog_raw.json"
OUTPUT_PATH = Path(__file__).parent / "catalog.json"
MIN_RECORDS = 377

TEST_TYPE_MAP = {
    "A": "Ability & Aptitude",
    "B": "Biodata & Situational Judgement",
    "C": "Competencies",
    "D": "Development & 360",
    "E": "Assessment Exercises",
    "K": "Knowledge & Skills",
    "P": "Personality & Behavior",
    "S": "Simulations",
}


# ─── Cleaning helpers ─────────────────────────────────────────────────────────

def _clean_str(value) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _clean_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = [_clean_str(v) for v in value]
    return [v for v in cleaned if v]


def _parse_duration(value) -> int | None:
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        m = re.search(r"\d+", value)
        if m:
            return int(m.group())
    return None


def build_search_text(record: dict) -> str:
    """
    Concatenates all semantically meaningful fields into a single string
    used for embedding. Richer text → better retrieval quality.

    Format:
        {name}. {description}
        Test types: {types}.
        Job levels: {levels}.
        Duration: {dur} minutes.
        Remote testing: {yes/no}. Adaptive: {yes/no}.
    """
    parts = []

    name = record.get("name", "")
    if name:
        parts.append(name + ".")

    desc = record.get("description", "")
    if desc:
        parts.append(desc)

    types = record.get("test_types", [])
    if types:
        parts.append("Test types: " + ", ".join(types) + ".")

    levels = record.get("job_levels", [])
    if levels:
        parts.append("Job levels: " + ", ".join(levels) + ".")

    dur = record.get("duration")
    if dur is not None:
        parts.append(f"Duration: {dur} minutes.")

    remote = "Yes" if record.get("remote_testing") else "No"
    adaptive = "Yes" if record.get("adaptive") else "No"
    parts.append(f"Remote testing: {remote}. Adaptive: {adaptive}.")

    return " ".join(parts)


# ─── Validation ───────────────────────────────────────────────────────────────

REQUIRED_FIELDS = ["name", "url", "test_types"]


def validate(record: dict, idx: int) -> list[str]:
    """Return list of warning messages for incomplete record."""
    warnings = []
    for field in REQUIRED_FIELDS:
        val = record.get(field)
        if not val:
            warnings.append(f"Record #{idx} '{record.get('name', '?')}' missing: {field}")
    if record.get("url") and not record["url"].startswith("https://www.shl.com"):
        warnings.append(f"Record #{idx} has suspicious URL: {record['url']}")
    return warnings


# ─── Main pipeline ────────────────────────────────────────────────────────────

def clean_catalog(input_path: Path = INPUT_PATH, output_path: Path = OUTPUT_PATH) -> list[dict]:
    log.info("Loading raw catalog from: %s", input_path)
    with open(input_path, "r", encoding="utf-8") as f:
        raw: list[dict] = json.load(f)

    log.info("Loaded %d raw records.", len(raw))

    # ── 1. Deduplicate by URL ─────────────────────────────────────────────────
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for rec in raw:
        url = _clean_str(rec.get("url", ""))
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(rec)

    log.info("After deduplication: %d records (removed %d duplicates).",
             len(deduped), len(raw) - len(deduped))

    # ── 2. Normalise each record ──────────────────────────────────────────────
    cleaned: list[dict] = []
    all_warnings: list[str] = []

    for idx, rec in enumerate(deduped, start=1):
        # Resolve test_types from codes if needed
        codes = _clean_list(rec.get("test_type_codes", []))
        types = _clean_list(rec.get("test_types", []))
        if not types and codes:
            types = [TEST_TYPE_MAP.get(c, c) for c in codes]

        clean_rec = {
            "name":             _clean_str(rec.get("name", "")),
            "url":              _clean_str(rec.get("url", "")),
            "description":      _clean_str(rec.get("description", "")),
            "job_levels":       _clean_list(rec.get("job_levels", [])),
            "languages":        _clean_list(rec.get("languages", [])),
            "duration":         _parse_duration(rec.get("duration")),
            "remote_testing":   bool(rec.get("remote_testing", False)),
            "adaptive":         bool(rec.get("adaptive", False)),
            "test_type_codes":  [c.upper() for c in codes],
            "test_types":       types,
        }

        # Build embedding-friendly search_text
        clean_rec["search_text"] = build_search_text(clean_rec)

        # Validate
        warnings = validate(clean_rec, idx)
        all_warnings.extend(warnings)

        cleaned.append(clean_rec)

    # ── 3. Report validation issues ───────────────────────────────────────────
    if all_warnings:
        log.warning("%d validation warnings:", len(all_warnings))
        for w in all_warnings:
            log.warning("  %s", w)
    else:
        log.info("All records passed validation.")

    # ── 4. Final count check ──────────────────────────────────────────────────
    count = len(cleaned)
    if count < MIN_RECORDS:
        log.error(
            "Only %d records — below minimum of %d. "
            "Re-run scraper or check site changes.",
            count, MIN_RECORDS,
        )
    else:
        log.info("%d records — meets ≥%d requirement.", count, MIN_RECORDS)

    # ── 5. Save ───────────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2, ensure_ascii=False)

    log.info("Clean catalog saved → %s", output_path)
    return cleaned


def print_summary(catalog: list[dict]) -> None:
    """Print a quick summary of the cleaned catalog."""
    from collections import Counter

    type_counter: Counter = Counter()
    for rec in catalog:
        for t in rec.get("test_type_codes", []):
            type_counter[t] += 1

    print("\n" + "=" * 50)
    print(f"Catalog Summary — {len(catalog)} Individual Test Solutions")
    print("=" * 50)
    print(f"{'Test Type':<35} Count")
    print(f"{'-'*35}")
    for code in sorted(type_counter):
        label = TEST_TYPE_MAP.get(code, code)
        print(f"  {code} — {label:<30} {type_counter[code]}")
    print()

    no_desc  = sum(1 for r in catalog if not r["description"])
    no_dur   = sum(1 for r in catalog if r["duration"] is None)
    remote   = sum(1 for r in catalog if r["remote_testing"])
    adaptive = sum(1 for r in catalog if r["adaptive"])

    print(f"Missing description : {no_desc}")
    print(f"Missing duration    : {no_dur}")
    print(f"Remote testing      : {remote} ({remote/len(catalog)*100:.1f}%)")
    print(f"Adaptive            : {adaptive} ({adaptive/len(catalog)*100:.1f}%)")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    catalog = clean_catalog()
    print_summary(catalog)