import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from shl_scraper import scrape_catalog, save, OUTPUT_PATH as RAW_PATH
from catalog_cleaner import clean_catalog, print_summary, OUTPUT_PATH as CLEAN_PATH
from validate_catalog import validate


if __name__ == "__main__":
    # Step 1: Scrape
    catalog_raw = scrape_catalog()
    save(catalog_raw, RAW_PATH)

    # Step 2: Clean
    catalog = clean_catalog(RAW_PATH, CLEAN_PATH)
    print_summary(catalog)

    # Step 3: Validate
    validate(CLEAN_PATH)