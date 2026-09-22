# -*- coding: utf-8 -*-
"""Debate module — multi-agent structured debate and reflection."""

from src.agent.debate.backend import DebateBackend, DebateInput
from src.agent.debate.debate_arena import DebateArena
from src.agent.debate.debate_protocols import (
    Argument,
    DebateRound,
    DebateResult,
    DebateState,
    Rebuttal,
)
from src.agent.debate.moderator import DebateModerator
from src.agent.debate.internal_backend import InternalDebateBackend

__all__ = [
    "DebateArena",
    "DebateBackend",
    "DebateInput",
    "Argument",
    "DebateModerator",
    "DebateResult",
    "DebateRound",
    "DebateState",
    "InternalDebateBackend",
    "Rebuttal",
]
