# -*- coding: utf-8 -*-
"""Debate module — multi-agent structured debate and reflection."""

from src.agent.debate.debate_arena import DebateArena
from src.agent.debate.debate_protocols import (
    Argument,
    DebateRound,
    DebateResult,
    DebateState,
    Rebuttal,
)
from src.agent.debate.moderator import DebateModerator

__all__ = [
    "DebateArena",
    "Argument",
    "DebateModerator",
    "DebateResult",
    "DebateRound",
    "DebateState",
    "Rebuttal",
]
