"""
Pydantic models for structured LLM outputs.

Used with Anthropic tool_use to guarantee valid, typed JSON from agent calls.
Replaces fragile regex/json.loads patterns across the pipeline.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AdversaryVerdict(BaseModel):
    verdict: Literal["PASS", "CHALLENGE"]
    challenges: list[str] = Field(default_factory=list)
    risk_override: int = Field(default=0, ge=0, le=30)


class TraderThesis(BaseModel):
    thesis: str = Field(description="2-3 sentence trade thesis explaining WHY this trade NOW")
    edge: str = Field(description="Specific edge — why will this move and what makes this high probability")
    risk: str = Field(description="Primary risk that would invalidate this setup")
    conviction: int = Field(description="Conviction score 0-100", ge=0, le=100)
    timing: Literal["swing", "position"] = Field(description="swing=1-5 days, position=1-2 months")


class TraderRebuttal(BaseModel):
    stance: Literal["MAINTAIN", "REVISE"]
    response: str = Field(description="Direct response to each adversary challenge, 2-4 sentences")
    revised_conviction: int = Field(
        description="Updated conviction after considering challenges. If MAINTAIN, can be same or higher. If REVISE, must be lower.",
        ge=0, le=100,
    )


class RiskAssessment(BaseModel):
    verdict: Literal["APPROVE", "CONDITIONAL_APPROVE", "REJECT"]
    reasoning: str = Field(description="2-3 sentence explanation")
    conditions: str = Field(default="", description="Required conditions if CONDITIONAL_APPROVE, empty otherwise")
