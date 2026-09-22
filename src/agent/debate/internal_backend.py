"""Adapter that preserves the original DebateArena implementation."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from src.agent.debate.debate_arena import DebateArena


class InternalDebateBackend:
    """Expose the original arena through the pluggable backend contract."""

    def __init__(self, llm_adapter, config=None, skill_memory=None, episode_store=None, debate_tracker=None):
        self.llm_adapter = llm_adapter
        self.config = config
        self.skill_memory = skill_memory
        self.episode_store = episode_store
        self.debate_tracker = debate_tracker

    def debate(
        self,
        context,
        technical_opinion=None,
        intel_opinion=None,
        risk_opinion=None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        timeout: Optional[float] = None,
    ):
        result = DebateArena(
            self.llm_adapter,
            config=self.config,
            skill_memory=self.skill_memory,
            episode_store=self.episode_store,
            debate_tracker=self.debate_tracker,
        ).debate(
            context,
            technical_opinion=technical_opinion,
            intel_opinion=intel_opinion,
            risk_opinion=risk_opinion,
            progress_callback=progress_callback,
            timeout=timeout,
        )
        result.backend = "internal"
        return result
