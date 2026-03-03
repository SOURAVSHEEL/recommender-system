"""
shl_scraper.py
==============
Scrapes the SHL product catalog for all Individual Test Solutions (type=1).
Skips Pre-packaged Job Solutions (type=2) entirely.

Pagination URL pattern:
  https://www.shl.com/products/product-catalog/?start={offset}&type=1
  - 12 items per page
  - Individual Test Solutions: ~32 pages (≥377 items)

Detail page fields extracted per assessment:
  - name          : str
  - url           : str  (canonical absolute URL)
  - description   : str
  - job_levels    : list[str]
  - languages     : list[str]
  - duration      : int | None  (minutes; None if not listed)
  - remote_testing: bool
  - adaptive      : bool
  - test_types    : list[str]   (e.g. ["A", "K"])

Output: scraper/catalog_raw.json
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ─── Config ──────────────────────────────────────────────────────────────────

BASE_URL       = "https://www.shl.com"
CATALOG_URL    = f"{BASE_URL}/products/product-catalog/"
PAGE_SIZE      = 12          # SHL shows 12 rows per page
TYPE_INDIVIDUAL = 1          # type=1  →  Individual Test Solutions
REQUEST_DELAY  = 1.2         # seconds between HTTP requests (polite crawling)
MAX_RETRIES    = 3
OUTPUT_PATH    = Path(__file__).parent / "catalog_raw.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Map badge letter → full label used in the catalog
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

def get_url(url: str, params: dict = None) -> Optional[BeautifulSoup]:
    """GET with retry logic; returns BeautifulSoup or None on failure."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as exc:
            log.warning("Attempt %d/%d failed for %s — %s", attempt, MAX_RETRIES, url, exc)
            if attempt < MAX_RETRIES:
                time.sleep(REQUEST_DELAY * attempt * 2)
    log.error("All retries exhausted for %s", url)
    return None


# ─── Catalog listing page parser ─────────────────────────────────────────────

def parse_listing_page(soup: BeautifulSoup) -> list[dict]:
    """
    Extract rows from the 'Individual Test Solutions' table on a catalog page.

    Returns a list of dicts with keys:
        name, url, remote_testing, adaptive, test_type_codes
    """
    rows = []

    # Find the correct table — the one whose preceding <h2>/<th> says
    # 'Individual Test Solutions'.  The page has two tables: one for
    # Pre-packaged Job Solutions and one for Individual Test Solutions.
    tables = soup.find_all("table")
    target_table = None
    for table in tables:
        header_row = table.find("tr")
        if header_row:
            th_text = header_row.get_text(" ", strip=True)
            if "Individual Test Solutions" in th_text:
                target_table = table
                break

    if target_table is None:
        log.debug("Individual Test Solutions table not found on this page.")
        return rows

    for tr in target_table.find_all("tr")[1:]:  # skip header row
        tds = tr.find_all("td")
        if not tds:
            continue

        # ── Column 0: name + link ────────────────────────────────────────────
        a_tag = tds[0].find("a")
        if not a_tag:
            continue
        name = a_tag.get_text(strip=True)
        href = a_tag.get("href", "")
        url  = urljoin(BASE_URL, href)

        # ── Column 1: Remote Testing icon (img present = Yes) ────────────────
        remote_testing = bool(tds[1].find("img")) if len(tds) > 1 else False

        # ── Column 2: Adaptive/IRT icon ──────────────────────────────────────
        adaptive = bool(tds[2].find("img")) if len(tds) > 2 else False

        # ── Column 3: Test type badges  e.g. [C][P][A][B] ───────────────────
        test_type_codes = []
        if len(tds) > 3:
            for span in tds[3].find_all("span"):
                code = span.get_text(strip=True).upper()
                if code in TEST_TYPE_MAP:
                    test_type_codes.append(code)

        rows.append({
            "name": name,
            "url": url,
            "remote_testing": remote_testing,
            "adaptive": adaptive,
            "test_type_codes": test_type_codes,
        })

    return rows


def get_total_pages(soup: BeautifulSoup) -> int:
    """
    Read the last pagination link to determine total page count for type=1.
    Falls back to a high ceiling (50) if pagination can't be parsed.
    """
    # Pagination links look like:  /products/product-catalog/?start=372&type=1
    # The last numbered link before 'Next' gives us the final page start offset.
    last_start = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "type=1" in href:
            m = re.search(r"start=(\d+)", href)
            if m:
                last_start = max(last_start, int(m.group(1)))

    if last_start == 0:
        log.warning("Could not determine pagination; defaulting to 50 pages.")
        return 50

    total_pages = (last_start // PAGE_SIZE) + 1
    log.info("Detected %d pages (last start offset = %d)", total_pages, last_start)
    return total_pages


# ─── Detail page parser ───────────────────────────────────────────────────────

def parse_detail_page(soup: BeautifulSoup, url: str) -> dict:
    """
    Extract rich metadata from an individual assessment detail page.
    Returns a dict merging with the listing-level fields.
    """
    detail = {"url": url}

    # ── Description ──────────────────────────────────────────────────────────
    # Sits inside an <h4> labelled "Description" followed by <p> tags
    desc_parts = []
    desc_header = soup.find("h4", string=re.compile(r"Description", re.I))
    if desc_header:
        for sib in desc_header.find_next_siblings():
            if sib.name and sib.name.startswith("h"):
                break          # stop at next section heading
            text = sib.get_text(" ", strip=True)
            if text:
                desc_parts.append(text)
    detail["description"] = " ".join(desc_parts).strip()

    # ── Job levels ───────────────────────────────────────────────────────────
    job_header = soup.find("h4", string=re.compile(r"Job levels?", re.I))
    if job_header:
        raw = job_header.find_next_sibling()
        if raw:
            detail["job_levels"] = [
                j.strip() for j in raw.get_text(",", strip=True).split(",") if j.strip()
            ]
        else:
            detail["job_levels"] = []
    else:
        detail["job_levels"] = []

    # ── Languages ────────────────────────────────────────────────────────────
    lang_header = soup.find("h4", string=re.compile(r"Languages?", re.I))
    if lang_header:
        raw = lang_header.find_next_sibling()
        if raw:
            detail["languages"] = [
                la.strip() for la in raw.get_text(",", strip=True).split(",") if la.strip()
            ]
        else:
            detail["languages"] = []
    else:
        detail["languages"] = []

    # ── Duration (minutes) ───────────────────────────────────────────────────
    # Text pattern: "Approximate Completion Time in minutes = 20"
    duration_header = soup.find("h4", string=re.compile(r"Assessment length", re.I))
    detail["duration"] = None
    if duration_header:
        raw = duration_header.find_next_sibling()
        if raw:
            m = re.search(r"=\s*(\d+)", raw.get_text())
            if m:
                detail["duration"] = int(m.group(1))
        # Also try direct text inside the h4's parent section
    if detail["duration"] is None:
        m = re.search(r"Completion Time in minutes\s*=\s*(\d+)", soup.get_text())
        if m:
            detail["duration"] = int(m.group(1))

    return detail


# ─── Main orchestration ───────────────────────────────────────────────────────

def scrape_catalog() -> list[dict]:
    """
    Full pipeline:
    1. Paginate listing pages to collect all assessment stubs.
    2. Fetch each detail page to enrich each stub.
    3. Return the merged list.
    """
    # ── Step 1: Discover all pages ───────────────────────────────────────────
    log.info("Fetching first catalog page to detect pagination ...")
    first_soup = get_url(CATALOG_URL, params={"start": 0, "type": TYPE_INDIVIDUAL})
    if first_soup is None:
        raise RuntimeError("Failed to fetch the first catalog page. Aborting.")

    total_pages = get_total_pages(first_soup)

    # ── Step 2: Collect all listing rows ─────────────────────────────────────
    stubs: list[dict] = []
    seen_urls: set[str] = set()

    for page_num in range(total_pages):
        start_offset = page_num * PAGE_SIZE
        log.info("Scraping listing page %d/%d (start=%d) ...", page_num + 1, total_pages, start_offset)

        if page_num == 0:
            soup = first_soup
        else:
            time.sleep(REQUEST_DELAY)
            soup = get_url(CATALOG_URL, params={"start": start_offset, "type": TYPE_INDIVIDUAL})
            if soup is None:
                log.warning("Skipping page %d — fetch failed.", page_num + 1)
                continue

        rows = parse_listing_page(soup)
        if not rows:
            log.info("No rows found on page %d — stopping early.", page_num + 1)
            break

        for row in rows:
            if row["url"] not in seen_urls:
                stubs.append(row)
                seen_urls.add(row["url"])

        log.info(" %d rows collected so far (this page: %d)", len(stubs), len(rows))

    log.info("Listing phase complete. Total unique assessments found: %d", len(stubs))

    # ── Step 3: Enrich each stub with detail-page data ───────────────────────
    catalog: list[dict] = []

    for idx, stub in enumerate(stubs, 1):
        log.info("[%d/%d] Fetching detail: %s", idx, len(stubs), stub["url"])
        time.sleep(REQUEST_DELAY)

        detail_soup = get_url(stub["url"])
        if detail_soup is None:
            log.warning("Detail fetch failed — storing partial record.")
            detail = {"description": "", "job_levels": [], "languages": [], "duration": None}
        else:
            detail = parse_detail_page(detail_soup, stub["url"])

        # Merge listing stub + detail
        record = {
            "name":stub["name"],
            "url":stub["url"],
            "description":detail.get("description", ""),
            "job_levels":detail.get("job_levels", []),
            "languages":detail.get("languages", []),
            "duration":detail.get("duration"),
            "remote_testing":stub["remote_testing"],
            "adaptive":stub["adaptive"],
            "test_type_codes":stub["test_type_codes"],
            "test_types":     [
                TEST_TYPE_MAP.get(c, c) for c in stub["test_type_codes"]
            ],
        }
        catalog.append(record)

        # Save checkpoint every 50 records
        if idx % 50 == 0:
            save(catalog, OUTPUT_PATH)
            log.info("  Checkpoint saved (%d records).", idx)

    return catalog


def save(catalog: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    log.info("Saved %d records → %s", len(catalog), path)


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("SHL Product Catalog Scraper Starting")
    catalog = scrape_catalog()
    save(catalog, OUTPUT_PATH)
    log.info("Done. Total records: %d ", len(catalog))
    if len(catalog) < 377:
        log.warning(
            "WARNING: Only %d records scraped — expected ≥377. "
            "Check pagination or site changes.",
            len(catalog),
        )
    else:
        log.info("Product Catalog scraped")