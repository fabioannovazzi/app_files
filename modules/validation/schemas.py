from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ClaimIssue:
    id: str
    description: str
    proposed_fix: str = ""
    auto_fixable: bool = False
    gravity: Optional[str] = None
    confidence: Optional[float] = None
    risk_score: Optional[int] = None
    risk_band: Optional[str] = None
    risk_factors: List[str] = field(default_factory=list)


@dataclass
class ClaimResult:
    claim_index: int
    claim_text: str
    reference_urls: List[str]
    issues: List[ClaimIssue] = field(default_factory=list)


@dataclass
class ResearchVerificationOutput:
    language: str
    claims: List[ClaimResult]
    correction_prompt: Optional[str] = None
    updated_document: Optional[str] = None  # markdown text


__all__ = ["ClaimIssue", "ClaimResult", "ResearchVerificationOutput"]
