"""Backend contracts for pluggable debate orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from src.agent.protocols import AgentContext, AgentOpinion
    from src.agent.debate.debate_protocols import DebateResult


@dataclass(frozen=True)
class DebateInput:
    """Bounded, JSON-safe input shared by debate backends."""

    query: str = ""
    stock_code: str = ""
    stock_name: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    opinions: Dict[str, Optional["AgentOpinion"]] = field(default_factory=dict)
    risk_flags: List[Dict[str, Any]] = field(default_factory=list)


class DebateBackend(Protocol):
    """Common contract implemented by internal and external debate engines."""

    def debate(
        self,
        context: "AgentContext",
        technical_opinion: Optional["AgentOpinion"] = None,
        intel_opinion: Optional["AgentOpinion"] = None,
        risk_opinion: Optional["AgentOpinion"] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        timeout: Optional[float] = None,
    ) -> "DebateResult":
        ...
