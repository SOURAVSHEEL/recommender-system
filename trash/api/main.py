"""
main.py — FastAPI application

Endpoints:
  GET  /health     → {"status": "healthy"}
  POST /recommend  → {"recommended_assessments": [...]}

Run:
  uvicorn api.main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.models import RecommendRequest, RecommendResponse, Assessment
from api.recommender import recommend

app = FastAPI(title="SHL Assessment Recommender", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/recommend", response_model=RecommendResponse)
def recommend_assessments(request: RecommendRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    results = recommend(request.query)

    if not results:
        raise HTTPException(status_code=404, detail="No relevant assessments found")

    return RecommendResponse(
        recommended_assessments=[Assessment(**r) for r in results]
    )