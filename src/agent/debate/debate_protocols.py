# -*- coding: utf-8 -*-
"""
Debate protocols — structured data types for multi-agent debate rounds.

Provides the foundational types that DebateArena, AdvocateAgents, and the
Moderator share during a structured debate session.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.agent.protocols import Signal, AgentOpinion


# ============================================================
# Debate-specific Argument / Rebuttal types
# ============================================================

@dataclass
class Argument:
    """A single argument produced by an advocate in a debate round."""
    advocate: str = ""  # e.g. "bull_advocate", "bear_advocate"
    signal: str = ""    # buy / hold / sell
    confidence: float = 0.5
    reasoning: str = ""
    key_evidence: List[str] = field(default_factory=list)
    # e.g. ["北向资金连续3日净流入", "MACD底背离形成"]
    raw_data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, float(self.confidence)))


@dataclass
class Rebuttal:
    """A rebuttal from one advocate targeting another's argument."""
    from_advocate: str = ""
    target_advocate: str = ""
    rebuttal_text: str = ""
    # Which parts of the target's argument are contested
    contested_points: List[str] = field(default_factory=list)
    # Counter-evidence offered
    counter_evidence: List[str] = field(default_factory=list)
    # Does the rebuttal change the advocate's own stance?
    revised_signal: Optional[str] = None
    revised_confidence: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.revised_confidence is not None:
            self.revised_confidence = max(0.0, min(1.0, float(self.revised_confidence)))


@dataclass
class DebateRound:
    """One complete round of structured debate."""
    round_number: int = 0
    bull_argument: Optional[Argument] = None
    bear_argument: Optional[Argument] = None
    risk_comment: Optional[Argument] = None
    bull_rebuttal: Optional[Rebuttal] = None
    bear_rebuttal: Optional[Rebuttal] = None
    risk_commentary: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def signals(self) -> List[str]:
        """Return all signals in this round."""
        signals = []
        if self.bull_argument:
            signals.append(self.bull_argument.signal)
        if self.bear_argument:
            signals.append(self.bear_argument.signal)
        return signals

    @property
    def max_confidence(self) -> float:
        """Return max confidence across arguments in this round."""
        confs = []
        if self.bull_argument:
            confs.append(self.bull_argument.confidence)
        if self.bear_argument:
            confs.append(self.bear_argument.confidence)
        return max(confs) if confs else 0.0

    def to_summary(self) -> str:
        """Brief text summary for injecting into next round's context."""
        parts = []
        if self.bull_argument:
            parts.append(f"[多方] 信号:{self.bull_argument.signal} 置信度:{self.bull_argument.confidence:.2f}")
            parts.append(f"理由: {self.bull_argument.reasoning}")
        if self.bear_argument:
            parts.append(f"[空方] 信号:{self.bear_argument.signal} 置信度:{self.bear_argument.confidence:.2f}")
            parts.append(f"理由: {self.bear_argument.reasoning}")
        if self.bull_rebuttal:
            parts.append(f"[多方反驳] {self.bull_rebuttal.rebuttal_text}")
        if self.bear_rebuttal:
            parts.append(f"[空方反驳] {self.bear_rebuttal.rebuttal_text}")
        if self.risk_commentary:
            parts.append(f"[风控点评] {self.risk_commentary}")
        return "\n".join(parts)


@dataclass
class DebateState:
    """Mutable state carried through the entire debate session."""
    stock_code: str = ""
    stock_name: str = ""
    rounds: List[DebateRound] = field(default_factory=list)
    bull_opinion: Optional[AgentOpinion] = None
    bear_opinion: Optional[AgentOpinion] = None
    risk_opinion: Optional[AgentOpinion] = None
    technical_opinion: Optional[AgentOpinion] = None
    intel_opinion: Optional[AgentOpinion] = None
    context_data: Dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    concluded: bool = False


@dataclass
class DebateResult:
    """Final result from a completed debate."""
    success: bool = False
    rounds_completed: int = 0
    final_signal: str = "hold"
    final_confidence: float = 0.5
    final_reasoning: str = ""
    consensus_reached: bool = False
    convergence_round: int = 0
    all_rounds: List[DebateRound] = field(default_factory=list)
    moderator_summary: str = ""
    dashboard: Optional[Dict[str, Any]] = None
    duration_s: float = 0.0
    tokens_used: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "final_signal": self.final_signal,
            "final_confidence": round(self.final_confidence, 2),
            "final_reasoning": self.final_reasoning,
            "consensus_reached": self.consensus_reached,
            "rounds_completed": self.rounds_completed,
            "convergence_round": self.convergence_round,
            "moderator_summary": self.moderator_summary,
            "duration_s": round(self.duration_s, 2),
            "tokens_used": self.tokens_used,
        }
