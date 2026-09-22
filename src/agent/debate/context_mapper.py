"""Convert mutable FinAgent context into a bounded debate snapshot."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.agent.debate.backend import DebateInput
from src.agent.protocols import AgentContext, AgentOpinion

_MAX_TEXT_LENGTH = 12_000


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:_MAX_TEXT_LENGTH]
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for key, item in value.items():
            safe_item = _json_safe(item)
            if safe_item is not _UNSUPPORTED:
                result[str(key)] = safe_item
        return result
    if isinstance(value, (list, tuple, set)):
        return [safe_item for item in value if (safe_item := _json_safe(item)) is not _UNSUPPORTED]
    return _UNSUPPORTED


class _Unsupported:
    pass


_UNSUPPORTED = _Unsupported()


def _copy_opinion(opinion: Optional[AgentOpinion]) -> Optional[AgentOpinion]:
    if opinion is None:
        return None
    return AgentOpinion(
        agent_name=opinion.agent_name,
        signal=opinion.signal,
        confidence=opinion.confidence,
        reasoning=opinion.reasoning[:_MAX_TEXT_LENGTH],
        key_levels=dict(opinion.key_levels),
        raw_data=_json_safe(opinion.raw_data) if isinstance(_json_safe(opinion.raw_data), dict) else {},
        timestamp=opinion.timestamp,
    )


def build_debate_input(context: AgentContext, **opinions: Optional[AgentOpinion]) -> DebateInput:
    """Build a safe snapshot and omit runtime-only objects from context data."""
    safe_data = _json_safe(context.data)
    if not isinstance(safe_data, dict):
        safe_data = {}

    selected_opinions = {
        name: _copy_opinion(opinion)
        for name, opinion in opinions.items()
    }
    safe_risk_flags = _json_safe(context.risk_flags)
    if not isinstance(safe_risk_flags, list):
        safe_risk_flags = []

    return DebateInput(
        query=context.query[:_MAX_TEXT_LENGTH],
        stock_code=context.stock_code,
        stock_name=context.stock_name[:_MAX_TEXT_LENGTH],
        data=safe_data,
        opinions=selected_opinions,
        risk_flags=safe_risk_flags,
    )
