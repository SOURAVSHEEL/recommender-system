"""
models.py — Pydantic request / response schemas
"""

from typing import Optional
from pydantic import BaseModel, HttpUrl


class RecommendRequest(BaseModel):
    query: str


class Assessment(BaseModel):
    name: str
    url: str
    description: str
    duration: Optional[int]
    remote_support: str        # "Yes" / "No"
    adaptive_support: str      # "Yes" / "No"
    test_type: list[str]       # e.g. ["Knowledge & Skills", "Personality & Behavior"]


class RecommendResponse(BaseModel):
    recommended_assessments: list[Assessment]