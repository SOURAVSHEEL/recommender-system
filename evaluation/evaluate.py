"""
evaluate.py  —  SHL Assessment Recommender Evaluation
======================================================
Hits a live /recommend API and computes:
  • Recall@1, @5, @10
  • Precision@1, @5, @10
  • Mean Recall@10  (primary submission metric)

Usage:
    Set API_BASE_URL and TRAIN_CSV below, then run:
        python evaluate.py
"""

import csv
import io
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

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE_URL = "http://localhost:8000"
TRAIN_CSV    = "Gen_AI_Dataset_xlsx_-_Train-Set__1_.csv"
K_VALUES     = [1, 5, 10]
TIMEOUT      = 90   # seconds per request
# ─────────────────────────────────────────────────────────────────────────────


def url_to_slug(url: str) -> str:
    """Normalise both SHL URL variants to the final path slug for comparison."""
    return url.strip().rstrip("/").split("/")[-1].lower()


def recall_at_k(predicted: list, relevant: list, k: int) -> float:
    """Recall@K = |relevant ∩ top-K predicted| / |relevant|"""
    if not relevant:
        return 0.0
    top_k   = {url_to_slug(u) for u in predicted[:k]}
    rel_set = {url_to_slug(u) for u in relevant}
    return len(top_k & rel_set) / len(rel_set)


def precision_at_k(predicted: list, relevant: list, k: int) -> float:
    """Precision@K = |relevant ∩ top-K predicted| / K"""
    if k == 0:
        return 0.0
    top_k   = {url_to_slug(u) for u in predicted[:k]}
    rel_set = {url_to_slug(u) for u in relevant}
    return len(top_k & rel_set) / k


def load_ground_truth(csv_path: str) -> list:
    """
    Load train CSV with schema:  Query | Assessment_url  (long-form, one URL per row)
    Returns: [{"query": str, "relevant_urls": [str, ...]}, ...]
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    with open(path, encoding="utf-8-sig") as f:
        content = f.read()

    records: dict = {}
    for row in csv.DictReader(io.StringIO(content)):
        q = row.get("Query", "").strip()
        u = row.get("Assessment_url", "").strip().rstrip("/")
        if q and u.startswith("http"):
            records.setdefault(q, []).append(u)

    result = [{"query": q, "relevant_urls": urls} for q, urls in records.items()]
    log.info("Loaded %d queries, %d total relevant URLs",
             len(result), sum(len(r["relevant_urls"]) for r in result))
    return result


def query_api(query: str) -> list:
    """POST /recommend → list of predicted URLs in rank order."""
    try:
        t0   = time.time()
        resp = requests.post(
            API_BASE_URL.rstrip("/") + "/recommend",
            json={"query": query},
            timeout=TIMEOUT,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        urls = [a["url"] for a in resp.json().get("recommended_assessments", [])]
        log.info("  %.2fs → %d results", time.time() - t0, len(urls))
        return urls
    except Exception as exc:
        log.warning("  API error: %s", exc)
        return []


def evaluate():
    ground_truth = load_ground_truth(TRAIN_CSV)
    n = len(ground_truth)

    # Accumulate scores per K
    recall_scores    = {k: [] for k in K_VALUES}
    precision_scores = {k: [] for k in K_VALUES}

    for i, rec in enumerate(ground_truth, 1):
        q   = rec["query"]
        rel = rec["relevant_urls"]

        log.info("[%d/%d] %s", i, n, q[:80].replace("\n", " "))
        predicted = query_api(q)

        for k in K_VALUES:
            recall_scores[k].append(recall_at_k(predicted, rel, k))
            precision_scores[k].append(precision_at_k(predicted, rel, k))

    # ── Print results ─────────────────────────────────────────────────────
    WIDTH = 52
    print("\n" + "=" * WIDTH)
    print("SHL RECOMMENDER — EVALUATION RESULTS")
    print("=" * WIDTH)
    print(f"{'Metric':<22}  {'Score':>8}  {'%':>7}")
    print("  " + "-" * (WIDTH - 2))

    for k in K_VALUES:
        mean_r = sum(recall_scores[k])    / n
        mean_p = sum(precision_scores[k]) / n
        print(f"{'Recall@'+str(k):<22}  {mean_r:>8.4f}  {mean_r*100:>6.1f}%")
        print(f"{'Precision@'+str(k):<22}  {mean_p:>8.4f}  {mean_p*100:>6.1f}%")
        if k != K_VALUES[-1]:
            print()

    print("  " + "-" * (WIDTH - 2))
    primary = sum(recall_scores[10]) / n
    print(f"\nMean Recall@10 (primary): {primary:.4f}  ({primary*100:.1f}%)")
    print(f"Queries evaluated       : {n}")
    print("=" * WIDTH + "\n")


if __name__ == "__main__":
    evaluate()