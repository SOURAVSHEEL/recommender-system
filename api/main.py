"""
main.py — FastAPI app

Endpoints:
  GET  /health
  POST /recommend

Run:
  uvicorn api.main:app --reload --port 8000
"""

import logging
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from api.models import RecommendRequest, RecommendResponse, Assessment
from api.recommender import recommend
from api.url_fetcher import is_url, fetch_jd_from_url

log = logging.getLogger(__name__)

app = FastAPI(title="SHL Assessment Recommender", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    log.info("%s %s → %d (%.2fs)", request.method, request.url.path, response.status_code, time.time() - t0)
    return response


@app.get("/health")
def health():
    log.info("Health check OK")
    return {"status": "healthy"}


@app.post("/recommend", response_model=RecommendResponse)
def recommend_assessments(request: RecommendRequest):
    query = request.query.strip()
    log.info("Received /recommend request — query length: %d chars", len(query))

    if not query:
        log.warning("Empty query received")
        raise HTTPException(status_code=400, detail="query must not be empty")

    if is_url(query):
        log.info("Input detected as URL — fetching JD ...")
        try:
            query = fetch_jd_from_url(query)
        except Exception as e:
            log.error("URL fetch failed: %s", e)
            raise HTTPException(status_code=422, detail=f"Failed to fetch URL: {e}")

    results = recommend(query)

    if not results:
        log.warning("No assessments found for query")
        raise HTTPException(status_code=404, detail="No relevant assessments found")

    log.info("Returning %d assessments", len(results))
    return RecommendResponse(
        recommended_assessments=[Assessment(**r) for r in results]
    )