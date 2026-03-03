"""
models.py — Pydantic request/response schemas
"""

from typing import Optional
from pydantic import BaseModel


class RecommendRequest(BaseModel):
    query: str


class Assessment(BaseModel):
    name: str
    url: str
    description: str
    duration: Optional[int]
    remote_support: str       # "Yes" / "No"
    adaptive_support: str     # "Yes" / "No"
    test_type: list[str]      # ["Knowledge & Skills", "Personality & Behavior"]


class RecommendResponse(BaseModel):
    recommended_assessments: list[Assessment]