from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class ScoreDetail(BaseModel):
    score: float = Field(description="Score from 0.0 to 10.0")
    reasons: list[str] = Field(description="Bullet points explaining this score")


class RepoAnalysis(BaseModel):
    """Structured AI analysis of a GitHub repository.

    Kept separate from search/repo models so it is only
    populated on explicit user request, never during search.
    """
    repo_full_name: str

    summary: str = Field(description="What the project does in 2-3 sentences")
    target_audience: str = Field(description="Who this project is for")

    relevance_score: ScoreDetail = Field(
        description="Keyword match, topic match, language match — score 0-10"
    )
    health_score: ScoreDetail = Field(
        description="Recent activity, archived status, contributors, issue activity — score 0-10"
    )
    contribution_score: ScoreDetail = Field(
        description="Open issues, contributor count, project clarity, labels — score 0-10"
    )
    final_score: float = Field(
        description="Weighted combination of the three scores (0-10)"
    )
    verdict: Optional[str] = Field(
        default=None,
        description="One-line overall verdict for a developer evaluating this repo",
    )
