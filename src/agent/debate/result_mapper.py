"""Normalize external debate output into FinAgent's stable result contract."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from src.agent.debate.backend import DebateInput
from src.agent.debate.debate_protocols import DebateResult
from src.agent.protocols import normalize_decision_signal


def map_camel_result(
    payload: Mapping[str, Any],
    *,
    input_data: DebateInput,
    rounds_completed: int = 0,
    tokens_used: int = 0,
) -> DebateResult:
    """Map a CAMEL moderator object to the existing ``DebateResult`` type."""
    if not isinstance(payload, Mapping):
        raise ValueError("CAMEL result must be a mapping")

    raw_confidence = payload.get("confidence", payload.get("final_confidence", 0.5))
    try:
        confidence = max(0.0, min(1.0, float(raw_confidence)))
    except (TypeError, ValueError):
        confidence = 0.5

    dashboard = payload.get("dashboard")
    if not isinstance(dashboard, dict):
        dashboard = None

    return DebateResult(
        success=True,
        rounds_completed=max(0, int(rounds_completed)),
        final_signal=normalize_decision_signal(payload.get("final_signal", payload.get("decision_type", "hold"))),
        final_confidence=confidence,
        final_reasoning=str(payload.get("reasoning", payload.get("final_reasoning", "")) or ""),
        consensus_reached=bool(payload.get("consensus_reached", False)),
        convergence_round=int(payload.get("convergence_round", 0) or 0),
        moderator_summary=str(payload.get("moderator_summary", "") or ""),
        dashboard=dashboard,
        tokens_used=max(0, int(tokens_used or 0)),
    )
