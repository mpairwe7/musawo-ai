"""Routing state for Musawo mode supervisor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.models import Mode, Severity


@dataclass(frozen=True)
class RouteDecision:
    mode: Mode
    confidence: float
    severity_hint: Optional[Severity] = None
    clarification: Optional[str] = None
    escalation_reason: Optional[str] = None
    detected_symptoms: list[str] = field(default_factory=list)
