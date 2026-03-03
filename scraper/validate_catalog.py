"""
validate_catalog.py
===================
Quick smoke-test for catalog.json.
Run after catalog_cleaner.py to verify data quality before building the index.

Checks:
  - Count ≥ 377
  - All records have non-empty name + url
  - All URLs start with https://www.shl.com/products/product-catalog/view/
  - No duplicate URLs
  - At least 5 distinct test_type_codes exist across catalog
  - search_text field present and non-empty on all records
  - Prints per-type counts and sample records
"""

import json
import sys
from collections import Counter
from pathlib import Path

CATALOG_PATH = Path(__file__).parent / "catalog.json"
MIN_RECORDS  = 377
REQUIRED_URL_PREFIX = "https://www.shl.com/products/product-catalog/view/"


def validate(path: Path = CATALOG_PATH) -> bool:
    print(f"\nValidating: {path}")
    with open(path, "r", encoding="utf-8") as f:
        catalog: list[dict] = json.load(f)

    errors: list[str] = []
    warnings: list[str] = []

    # ── 1. Count ──────────────────────────────────────────────────────────────
    n = len(catalog)
    status = "Yes" if n >= MIN_RECORDS else "No"
    print(f"{status} Total records: {n}  (minimum: {MIN_RECORDS})")
    if n < MIN_RECORDS:
        errors.append(f"Only {n} records — need ≥{MIN_RECORDS}")

    # ── 2. Required fields ────────────────────────────────────────────────────
    missing_name = [r for r in catalog if not r.get("name")]
    missing_url  = [r for r in catalog if not r.get("url")]
    missing_text = [r for r in catalog if not r.get("search_text")]

    for field, bad in [("name", missing_name), ("url", missing_url), ("search_text", missing_text)]:
        if bad:
            errors.append(f"{len(bad)} records missing `{field}`")
            print(f"Missing `{field}`: {len(bad)} records")
        else:
            print(f"All records have `{field}`")

    # ── 3. URL format ─────────────────────────────────────────────────────────
    bad_urls = [r for r in catalog if not r.get("url", "").startswith(REQUIRED_URL_PREFIX)]
    if bad_urls:
        warnings.append(f"{len(bad_urls)} URLs don't start with expected prefix")
        print(f"{len(bad_urls)} URLs with unexpected prefix (showing first 3):")
        for r in bad_urls[:3]:
            print(f"      {r['url']}")
    else:
        print(f"All URLs match expected prefix")

    # ── 4. Duplicate URLs ─────────────────────────────────────────────────────
    url_counter = Counter(r.get("url", "") for r in catalog)
    dupes = {url: cnt for url, cnt in url_counter.items() if cnt > 1}
    if dupes:
        errors.append(f"{len(dupes)} duplicate URLs")
        print(f"Duplicate URLs: {len(dupes)}")
    else:
        print(f"No duplicate URLs")

    # ── 5. Test type coverage ─────────────────────────────────────────────────
    type_counter: Counter = Counter()
    for rec in catalog:
        for code in rec.get("test_type_codes", []):
            type_counter[code] += 1

    print(f"\n  Test type distribution:")
    type_labels = {
        "A": "Ability & Aptitude",
        "B": "Biodata & Situational Judgement",
        "C": "Competencies",
        "D": "Development & 360",
        "E": "Assessment Exercises",
        "K": "Knowledge & Skills",
        "P": "Personality & Behavior",
        "S": "Simulations",
    }
    for code in sorted(type_counter):
        label = type_labels.get(code, code)
        bar = "█" * (type_counter[code] // 10)
        print(f"    {code} {label:<35} {type_counter[code]:>4}  {bar}")

    if len(type_counter) < 5:
        errors.append(f"Only {len(type_counter)} distinct test types — expected ≥5")

    # ── 6. Duration stats ─────────────────────────────────────────────────────
    durations = [r["duration"] for r in catalog if r.get("duration") is not None]
    no_dur    = n - len(durations)
    if durations:
        avg = sum(durations) / len(durations)
        print(f"\nDuration stats:")
        print(f"With duration: {len(durations)} records")
        print(f"Without duration: {no_dur} records")
        print(f"Min / Avg / Max : {min(durations)} / {avg:.1f} / {max(durations)} minutes")

    # ── 7. Sample records ─────────────────────────────────────────────────────
    print(f"\n  Sample records (first 3):")
    for rec in catalog[:3]:
        print(f"{rec['name']}")
        print(f"url: {rec['url']}")
        print(f"types: {rec['test_type_codes']}")
        print(f"duration: {rec['duration']} min")
        print(f"remote: {rec['remote_testing']}  adaptive: {rec['adaptive']}")
        print(f"desc: {rec['description'][:80]}...")
        print()

    # ── Result ────────────────────────────────────────────────────────────────
    print("  " + "─" * 48)
    if errors:
        print(f"FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"    • {e}")
        return False
    if warnings:
        print(f"PASSED WITH WARNINGS — {len(warnings)} warning(s):")
        for w in warnings:
            print(f"    • {w}")
    else:
        print(f"PASSED — catalog is clean and ready for indexing.")
    return True


if __name__ == "__main__":
    ok = validate()
    sys.exit(0 if ok else 1)