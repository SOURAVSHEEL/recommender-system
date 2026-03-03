"""
evaluate.py -- Evaluation harness for SHL Assessment Recommender
================================================================
Computes Mean Recall@K against the labeled ground-truth train set.

Key design decisions
--------------------
1.  Three-column CSV parsing
    The train CSV has the schema:  Query | Assessment_url | (alternate url)
    Both URL columns are collected as ground-truth for each query.

2.  Slug-based URL normalisation
    Ground-truth URLs come from two domains:
        https://www.shl.com/solutions/products/product-catalog/view/<slug>/
        https://www.shl.com/products/product-catalog/view/<slug>/
    The catalog (and therefore the API) only uses the /products/ form.
    Matching on full URL would score 0 for every /solutions/ URL.
    We normalise both to just the path slug for comparison.

3.  Timeout handling
    Ollama + Groq per query can take 30-60s. Default timeout is 90s.
    Use --timeout to adjust. Use --no-health-check if server is slow to start.

4.  Concurrency
    --workers N runs N queries in parallel (default 1 = sequential).
    Increase to 3-5 to speed up full evaluation runs.

Usage
-----
    # Live API evaluation (default data path)
    python evaluation/evaluate.py --api http://localhost:8000

    # Custom data file
    python evaluation/evaluate.py --api http://localhost:8000 --data "evaluation/Gen_AI Dataset.xlsx - Train-Set.csv"

    # Skip health check + long timeout for slow Ollama cold start
    python evaluation/evaluate.py --api http://localhost:8000 --no-health-check --timeout 120

    # Parallel queries (faster, but watch Ollama memory)
    python evaluation/evaluate.py --api http://localhost:8000 --workers 3

    # Offline eval from saved predictions
    python evaluation/evaluate.py --predictions evaluation/test_predictions.csv

    # Save predictions CSV for submission
    python evaluation/evaluate.py --api http://localhost:8000 --save-preds evaluation/submission.csv
"""

import argparse
import concurrent.futures
import csv
import io
import json
import logging
import time
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DEFAULT_TRAIN_CSV = "evaluation\Gen_AI Dataset.xlsx - Train-Set (1).csv"
DEFAULT_RESULTS   = "evaluation/results.json"


# ---------------------------------------------------------------------------
# URL normalisation
# ---------------------------------------------------------------------------

def url_to_slug(url: str) -> str:
    """
    Extract the path slug from any SHL assessment URL.

    Handles both domains:
        /solutions/products/product-catalog/view/<slug>/
        /products/product-catalog/view/<slug>/

    Returns the slug (lowercase, no trailing slash) for comparison.
    If the URL does not match the expected pattern, falls back to
    full-URL normalisation (lowercase, no trailing slash).

    Examples:
        url_to_slug("https://www.shl.com/solutions/products/product-catalog/view/java-8-new/")
        -> "java-8-new"
        url_to_slug("https://www.shl.com/products/product-catalog/view/java-8-new/")
        -> "java-8-new"
    """
    slug = url.strip().rstrip("/").split("/")[-1].lower()
    return slug


# ---------------------------------------------------------------------------
# Core metric
# ---------------------------------------------------------------------------

def recall_at_k(predicted: list, relevant: list, k: int = 10) -> float:
    """
    Recall@K = |relevant ∩ top-K predicted| / |relevant|

    Both lists are normalised to slugs before comparison so that
    /solutions/products/.../java-8-new  ==  /products/.../java-8-new.

    Returns float in [0.0, 1.0].  Returns 0.0 if relevant is empty.
    """
    if not relevant:
        return 0.0
    top_k   = {url_to_slug(u) for u in predicted[:k]}
    rel_set = {url_to_slug(u) for u in relevant}
    return len(top_k & rel_set) / len(rel_set)


# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------

def load_ground_truth(csv_path: str) -> list:
    """
    Load labeled ground-truth data.

    Handles the actual train-set format (3 columns):
        Query | Assessment_url | <alternate Assessment_url>

    Also handles the compact single-row format:
        query | relevant_urls   (comma-separated URLs in one cell)

    And the long-form submission format:
        query | Assessment_url  (one URL per row)

    Returns:
        list of {"query": str, "relevant_urls": list[str]}
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Ground-truth file not found: {csv_path}\n"
            "Pass the correct path with --data"
        )

    with open(path, encoding="utf-8-sig") as f:
        content = f.read()

    reader = csv.reader(io.StringIO(content))
    all_rows = list(reader)
    if not all_rows:
        raise ValueError(f"Empty CSV: {csv_path}")

    header = [h.strip() for h in all_rows[0]]
    data_rows = all_rows[1:]

    log.info("CSV columns: %s  (%d data rows)", header, len(data_rows))

    # ---- Detect format by header ----------------------------------------
    fn_lower = [h.lower() for h in header]

    # Format A: Query | Assessment_url | (optional extra url column)
    # This is the actual SHL train-set format — 2 or 3 URL columns possible
    if fn_lower[0] == "query" and any("assessment" in f for f in fn_lower[1:]):
        records: dict = {}
        for row in data_rows:
            if not row:
                continue
            q = row[0].strip()
            if not q:
                continue
            # Collect ALL non-empty URL values from columns 1 onward
            for cell in row[1:]:
                u = cell.strip().rstrip("/")
                if u and u.startswith("http"):
                    records.setdefault(q, []).append(u)
        result = [{"query": q, "relevant_urls": urls} for q, urls in records.items()]

    # Format B: query | relevant_urls  (comma-separated in single cell)
    elif "relevant_urls" in fn_lower or "relevant_url" in fn_lower:
        url_idx   = fn_lower.index("relevant_urls") if "relevant_urls" in fn_lower else fn_lower.index("relevant_url")
        query_idx = fn_lower.index("query")
        records = {}
        for row in data_rows:
            if len(row) <= max(query_idx, url_idx):
                continue
            q    = row[query_idx].strip()
            urls = [u.strip() for u in row[url_idx].split(",") if u.strip()]
            if q:
                records.setdefault(q, []).extend(urls)
        result = [{"query": q, "relevant_urls": urls} for q, urls in records.items()]

    else:
        raise ValueError(
            f"Cannot detect CSV format. Header: {header}\n"
            "Expected: 'Query, Assessment_url' or 'query, relevant_urls'"
        )

    log.info(
        "Loaded %d queries (%d total ground-truth URLs) from %s",
        len(result),
        sum(len(r["relevant_urls"]) for r in result),
        csv_path,
    )
    return result


def load_predictions_csv(csv_path: str) -> dict:
    """
    Load pre-generated predictions (long-form submission CSV).

    Format:  query | Assessment_url  (one URL per row)

    Returns: {query_str: [url1, url2, ...]}  (in file order = rank order)
    """
    preds: dict = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            q   = (row.get("query") or row.get("Query") or "").strip()
            url = (row.get("Assessment_url") or row.get("assessment_url") or "").strip()
            if q and url:
                preds.setdefault(q, []).append(url)
    log.info("Loaded predictions for %d queries from %s", len(preds), csv_path)
    return preds


# ---------------------------------------------------------------------------
# API interaction
# ---------------------------------------------------------------------------

def check_health(base_url: str, timeout: int = 30, retries: int = 3) -> bool:
    """Health check with retry + backoff for slow cold starts."""
    endpoint = base_url.rstrip("/") + "/health"
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(endpoint, timeout=timeout)
            if resp.status_code == 200:
                log.info("Health check passed (attempt %d): %s", attempt, base_url)
                return True
            log.warning("Health check HTTP %d (attempt %d/%d)",
                        resp.status_code, attempt, retries)
        except requests.exceptions.Timeout:
            log.warning("Health check timed out after %ds (attempt %d/%d)",
                        timeout, attempt, retries)
        except Exception as exc:
            log.warning("Health check error (attempt %d/%d): %s", attempt, retries, exc)

        if attempt < retries:
            wait = attempt * 5
            log.info("Retrying in %ds ...", wait)
            time.sleep(wait)

    log.error(
        "API health check failed after %d attempts.\n"
        "  Is the server running?  uvicorn api.main:app --reload --port 8000\n"
        "  Ollama slow to load?    Try --no-health-check --timeout 120",
        retries,
    )
    return False


def query_api(base_url: str, query: str, timeout: int = 90) -> list:
    """
    POST /recommend, return predicted URLs in rank order.
    Returns [] on any error (evaluation continues for other queries).
    """
    endpoint = base_url.rstrip("/") + "/recommend"
    try:
        t0   = time.time()
        resp = requests.post(
            endpoint,
            json={"query": query},
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        urls = [a["url"] for a in data.get("recommended_assessments", [])]
        log.info("  %.2fs -> %d assessments", time.time() - t0, len(urls))
        return urls
    except requests.exceptions.Timeout:
        log.warning("  Timed out after %ds  |  query: '%s'", timeout, query[:60])
        return []
    except Exception as exc:
        log.warning("  Error  |  query: '%s'  |  %s", query[:60], exc)
        return []


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def evaluate(ground_truth: list, predictions: dict, k: int = 10) -> dict:
    """
    Compute per-query Recall@K and Mean Recall@K.

    URL matching is done on slugs (last path segment) so that
    /solutions/products/.../java-8-new  matches  /products/.../java-8-new.
    """
    per_query      = []
    missing_queries = []

    for record in ground_truth:
        q    = record["query"]
        rel  = record["relevant_urls"]
        pred = predictions.get(q)

        if pred is None:
            # Fuzzy fallback: strip + lowercase
            pred = next(
                (v for k2, v in predictions.items()
                 if k2.strip().lower() == q.strip().lower()),
                None,
            )
            if pred is None:
                missing_queries.append(q)
                pred = []

        r        = recall_at_k(pred, rel, k=k)
        top_k    = {url_to_slug(u) for u in pred[:k]}
        rel_set  = {url_to_slug(u) for u in rel}
        hits     = len(top_k & rel_set)

        per_query.append({
            "query":     q,
            "recall":    round(r, 4),
            "hits":      hits,
            "relevant":  len(rel_set),
            "predicted": len(pred),
        })

    if missing_queries:
        log.warning(
            "%d queries had no predictions (scored as 0):\n%s",
            len(missing_queries),
            "\n".join(f"  - {q[:80]}" for q in missing_queries),
        )

    mean_recall = (
        sum(r["recall"] for r in per_query) / len(per_query)
        if per_query else 0.0
    )

    return {
        "mean_recall_at_k": round(mean_recall, 4),
        "k":                k,
        "n_queries":        len(per_query),
        "n_missing":        len(missing_queries),
        "per_query":        per_query,
    }


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def print_results(results: dict) -> None:
    k = results["k"]
    print("\n" + "=" * 74)
    print(f"  SHL RECOMMENDER EVALUATION  --  Mean Recall@{k}")
    print("=" * 74)
    print(f"\n{'#':>3}  {'Recall':>6}  {'Progress':<12}  {'Hits':>5}  Query")
    print("-" * 74)

    for i, row in enumerate(results["per_query"], 1):
        bar     = "#" * int(row["recall"] * 10)
        q_short = row["query"][:44].replace("\n", " ")
        q_short += "..." if len(row["query"]) > 44 else ""
        print(
            f"{i:>3}  {row['recall']:>6.4f}  [{bar:<10}]  "
            f"{row['hits']:>2}/{row['relevant']:<2}  {q_short}"
        )

    print("-" * 74)
    score = results["mean_recall_at_k"]
    print(f"\n  Mean Recall@{k}       :  {score:.4f}  ({score * 100:.1f}%)")
    print(f"  Queries evaluated   :  {results['n_queries']}")
    if results.get("n_missing"):
        print(f"  Missing predictions :  {results['n_missing']}  (counted as 0)")
    print("=" * 74 + "\n")


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_results(results: dict, path: str) -> None:
    """Append results to JSON, building an iteration history."""
    save_path = Path(path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    history = []
    if save_path.exists():
        try:
            existing = json.loads(save_path.read_text(encoding="utf-8"))
            history  = existing if isinstance(existing, list) else [existing]
        except Exception:
            history = []

    import datetime
    results["timestamp"] = datetime.datetime.now().isoformat()
    results["iteration"] = len(history) + 1
    history.append(results)

    save_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    log.info("Results saved -> %s  (iteration %d)", save_path, results["iteration"])


def save_predictions_csv(predictions: dict, path: str) -> None:
    """Save predictions to submission-format long-form CSV."""
    save_path = Path(path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["query", "Assessment_url"])
        for query, urls in predictions.items():
            for url in urls:
                writer.writerow([query, url])
    log.info(
        "Predictions saved -> %s  (%d rows)",
        save_path,
        sum(len(v) for v in predictions.values()),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate SHL Assessment Recommender -- Mean Recall@K",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Live API (default data path)
  python evaluation/evaluate.py --api http://localhost:8000

  # Custom data file
  python evaluation/evaluate.py --api http://localhost:8000 --data "evaluation/Gen_AI Dataset.xlsx - Train-Set.csv"

  # Skip health check + longer timeout (for slow Ollama cold start)
  python evaluation/evaluate.py --api http://localhost:8000 --no-health-check --timeout 120

  # Parallel queries to speed up full evaluation
  python evaluation/evaluate.py --api http://localhost:8000 --workers 3

  # Offline eval from saved predictions
  python evaluation/evaluate.py --predictions evaluation/test_predictions.csv

  # Save predictions CSV for submission
  python evaluation/evaluate.py --api http://localhost:8000 --save-preds evaluation/submission.csv
        """,
    )
    parser.add_argument("--data",       default=DEFAULT_TRAIN_CSV,
                        help=f"Ground-truth CSV  (default: {DEFAULT_TRAIN_CSV!r})")
    parser.add_argument("--api",        default=None,
                        help="API base URL, e.g. http://localhost:8000")
    parser.add_argument("--predictions",default=None,
                        help="Pre-generated predictions CSV (query, Assessment_url)")
    parser.add_argument("--k",          type=int, default=10,
                        help="Recall cutoff K  (default: 10)")
    parser.add_argument("--save",       default=DEFAULT_RESULTS,
                        help=f"Save results JSON  (default: {DEFAULT_RESULTS!r})")
    parser.add_argument("--save-preds", default=None, dest="save_preds",
                        help="Save API predictions to this CSV path")
    parser.add_argument("--no-health-check", action="store_true", dest="no_health_check",
                        help="Skip /health check (useful when Ollama is slow to load)")
    parser.add_argument("--timeout",    type=int, default=90,
                        help="Per-request timeout in seconds  (default: 90)")
    parser.add_argument("--workers",    type=int, default=1,
                        help="Parallel query workers  (default: 1 = sequential)")
    args = parser.parse_args()

    # ── Load ground truth ─────────────────────────────────────────────────
    ground_truth = load_ground_truth(args.data)

    # ── Get predictions ───────────────────────────────────────────────────
    predictions: dict = {}

    if args.api:
        if not args.no_health_check:
            if not check_health(args.api, timeout=args.timeout):
                log.error(
                    "Aborting.\n"
                    "  Start the server:  uvicorn api.main:app --reload --port 8000\n"
                    "  Or skip check:     --no-health-check"
                )
                return
        else:
            log.info("Skipping health check (--no-health-check)")

        log.info("Querying API for %d queries  (workers=%d, timeout=%ds) ...",
                 len(ground_truth), args.workers, args.timeout)

        def _run_one(record):
            q    = record["query"]
            urls = query_api(args.api, q, timeout=args.timeout)
            r    = recall_at_k(urls, record["relevant_urls"], k=args.k)
            log.info("[query done]  Recall@%d = %.4f  |  %s", args.k, r, q[:60].replace("\n"," "))
            return q, urls

        if args.workers > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
                for q, urls in pool.map(_run_one, ground_truth):
                    predictions[q] = urls
        else:
            for i, record in enumerate(ground_truth, 1):
                log.info("[%d/%d]  %s", i, len(ground_truth),
                         record["query"][:70].replace("\n", " "))
                q, urls = _run_one(record)
                predictions[q] = urls

        if args.save_preds:
            save_predictions_csv(predictions, args.save_preds)

    elif args.predictions:
        predictions = load_predictions_csv(args.predictions)

    else:
        parser.error("Provide either --api <url> or --predictions <csv_path>")
        return

    # ── Evaluate ──────────────────────────────────────────────────────────
    results = evaluate(ground_truth, predictions, k=args.k)
    print_results(results)

    # ── Save ─────────────────────────────────────────────────────────────
    if args.save:
        save_results(results, args.save)


# ---------------------------------------------------------------------------
# Importable helper
# ---------------------------------------------------------------------------

def compute_mean_recall(
    predictions: dict,
    ground_truth_path: str = DEFAULT_TRAIN_CSV,
    k: int = 10,
) -> float:
    """
    One-liner for notebooks / inline dev use.

    Args:
        predictions:        {query_str: [url1, url2, ...]}
        ground_truth_path:  path to labeled CSV
        k:                  cutoff

    Returns:
        Mean Recall@K as float

    Example:
        from evaluation.evaluate import compute_mean_recall
        score = compute_mean_recall(my_preds)
        print(f"Mean Recall@10: {score:.4f}")
    """
    gt = load_ground_truth(ground_truth_path)
    return evaluate(gt, predictions, k=k)["mean_recall_at_k"]


if __name__ == "__main__":
    main()