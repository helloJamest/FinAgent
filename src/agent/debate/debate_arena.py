# -*- coding: utf-8 -*-
"""
DebateArena — multi-agent structured debate controller.

Manages the lifecycle of Bull/Bear/Risk advocates across multiple debate
rounds, checking for convergence, and producing the final debate result.

Usage::

    arena = DebateArena(llm_adapter, config=config)
    result = arena.debate(context, technical_opinion, intel_opinion)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from src.agent.debate.advocate_agent import AdvocateAgent
from src.agent.debate.debate_protocols import (
    DebateResult,
    DebateRound,
    DebateState,
)
from src.agent.debate.moderator import DebateModerator

if TYPE_CHECKING:
    from src.agent.protocols import AgentContext, AgentOpinion

logger = logging.getLogger(__name__)

# Default configuration
_DEFAULT_MAX_ROUNDS = 3
_DEFAULT_CONSENSUS_THRESHOLD = 0.8
_DEFAULT_SIGNAL_CONVERGENCE = 1  # signal levels apart to consider converged


class DebateArena:
    """Multi-agent structured debate controller.

    Orchestrates Bull/Bear/Risk advocates through multiple debate rounds,
    checks for signal convergence, and uses a Moderator to produce the
    final decision.
    """

    def __init__(
        self,
        llm_adapter,
        config=None,
        skill_memory=None,
        episode_store=None,
        debate_tracker=None,
    ):
        self.llm_adapter = llm_adapter
        self.config = config
        self.skill_memory = skill_memory
        self.episode_store = episode_store
        self.debate_tracker = debate_tracker
        self.max_rounds = _DEFAULT_MAX_ROUNDS
        self.consensus_threshold = _DEFAULT_CONSENSUS_THRESHOLD
        self.signal_convergence = _DEFAULT_SIGNAL_CONVERGENCE
        self._load_config()

        # Create advocate agents and moderator
        self.bull_advocate = AdvocateAgent("bull", llm_adapter, config)
        self.bear_advocate = AdvocateAgent("bear", llm_adapter, config)
        self.moderator = DebateModerator(llm_adapter)

    def _load_config(self) -> None:
        """Load debate settings from config."""
        if self.config is None:
            return

        self.max_rounds = int(getattr(self.config, "debate_max_rounds", _DEFAULT_MAX_ROUNDS))
        self.consensus_threshold = float(getattr(self.config, "debate_consensus_threshold", _DEFAULT_CONSENSUS_THRESHOLD))
        self.signal_convergence = int(getattr(self.config, "debate_signal_convergence", _DEFAULT_SIGNAL_CONVERGENCE))

    def debate(
        self,
        context: "AgentContext",
        technical_opinion: Optional["AgentOpinion"] = None,
        intel_opinion: Optional["AgentOpinion"] = None,
        risk_opinion: Optional["AgentOpinion"] = None,
    ) -> DebateResult:
        """Run a structured debate and return the result."""
        t0 = time.time()
        total_tokens = 0

        # Initialise debate state
        state = DebateState(
            stock_code=context.stock_code,
            stock_name=context.stock_name,
            technical_opinion=technical_opinion,
            intel_opinion=intel_opinion,
            risk_opinion=risk_opinion,
            context_data=context.data,
        )

        # Collect context data for advocates
        context_data = self._collect_context_data(context, technical_opinion, intel_opinion, risk_opinion)

        # Hermes learning: retrieve relevant skills and inject into context
        retrieved_skills = self._retrieve_relevant_skills(context_data)
        if retrieved_skills:
            context_data["learned_skills"] = retrieved_skills
            context.set_data("learned_skills", retrieved_skills)

        logger.info(
            "[DebateArena] starting debate: %s (%s), max_rounds=%d",
            state.stock_code, state.stock_name, self.max_rounds,
        )

        # Round 1: Initial arguments
        bull_arg = self.bull_advocate.argue(context_data, state.stock_code, state.stock_name)
        bear_arg = self.bear_advocate.argue(context_data, state.stock_code, state.stock_name)

        round1 = DebateRound(
            round_number=1,
            bull_argument=bull_arg,
            bear_argument=bear_arg,
        )
        state.rounds.append(round1)

        logger.info(
            "[DebateArena] Round 1 — Bull: %s (%.2f), Bear: %s (%.2f)",
            bull_arg.signal, bull_arg.confidence,
            bear_arg.signal, bear_arg.confidence,
        )

        # Check for early convergence after Round 1
        if self._check_signal_convergence(state.rounds):
            logger.info("[DebateArena] converged after Round 1")
            state.concluded = True
            return self._finalize(state, t0, total_tokens, converged=True)

        # Rounds 2+: Rebuttals
        for round_num in range(2, self.max_rounds + 1):
            prev_round = state.rounds[-1]

            # Risk commentary (simple text synthesis)
            risk_comment = self._generate_risk_comment(state, risk_opinion)

            # Bull rebuts Bear
            bull_rebuttal = self.bull_advocate.rebut(
                opponent_argument=prev_round.bear_argument,
                your_previous=prev_round.bull_argument,
                risk_comments=risk_comment,
            )

            # Bear rebuts Bull
            bear_rebuttal = self.bear_advocate.rebut(
                opponent_argument=prev_round.bull_argument,
                your_previous=prev_round.bear_argument,
                risk_comments=risk_comment,
            )

            current_round = DebateRound(
                round_number=round_num,
                bull_rebuttal=bull_rebuttal,
                bear_rebuttal=bear_rebuttal,
                risk_commentary=risk_comment,
            )

            # Update signals from rebuttals
            if bull_rebuttal.revised_signal:
                current_round.bull_argument = bull_arg = type(prev_round.bull_argument)(
                    advocate=self.bull_advocate.agent_name,
                    signal=bull_rebuttal.revised_signal,
                    confidence=bull_rebuttal.revised_confidence or 0.5,
                    reasoning=bull_rebuttal.rebuttal_text,
                    key_evidence=bull_rebuttal.counter_evidence,
                )
            else:
                current_round.bull_argument = prev_round.bull_argument

            if bear_rebuttal.revised_signal:
                current_round.bear_argument = bear_arg = type(prev_round.bear_argument)(
                    advocate=self.bear_advocate.agent_name,
                    signal=bear_rebuttal.revised_signal,
                    confidence=bear_rebuttal.revised_confidence or 0.5,
                    reasoning=bear_rebuttal.rebuttal_text,
                    key_evidence=bear_rebuttal.counter_evidence,
                )
            else:
                current_round.bear_argument = prev_round.bear_argument

            state.rounds.append(current_round)

            logger.info(
                "[DebateArena] Round %d — Bull: %s, Bear: %s",
                round_num,
                current_round.bull_argument.signal if current_round.bull_argument else "N/A",
                current_round.bear_argument.signal if current_round.bear_argument else "N/A",
            )

            # Check convergence
            if self._check_signal_convergence(state.rounds):
                logger.info("[DebateArena] converged after Round %d", round_num)
                state.concluded = True
                return self._finalize(state, t0, total_tokens, converged=True)

        # Max rounds reached without convergence
        logger.info("[DebateArena] max rounds reached without convergence")
        return self._finalize(state, t0, total_tokens, converged=False)

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _check_signal_convergence(self, rounds: List[DebateRound]) -> bool:
        """Check if the latest round's signals have converged."""
        if not rounds:
            return False

        signal_order = {"strong_sell": 0, "sell": 1, "hold": 2, "buy": 3, "strong_buy": 4}
        latest = rounds[-1]

        signals = latest.signals
        if len(signals) < 2:
            return False

        positions = []
        for sig in signals:
            pos = signal_order.get(sig)
            if pos is not None:
                positions.append(pos)

        if not positions:
            return False

        return max(positions) - min(positions) <= self.signal_convergence

    def _generate_risk_comment(
        self,
        state: DebateState,
        risk_opinion: Optional["AgentOpinion"],
    ) -> str:
        """Generate a risk commentary text for the current debate state."""
        if risk_opinion and risk_opinion.reasoning:
            return risk_opinion.reasoning

        # Synthesize from risk flags in context
        parts = []
        if state.context_data.get("risk_flags"):
            for flag in state.context_data["risk_flags"][:3]:
                severity = flag.get("severity", "medium")
                desc = flag.get("description", "")
                parts.append(f"[{severity}] {desc}")

        return "\n".join(parts) if parts else "No significant risk flags identified."

    def _collect_context_data(
        self,
        context: "AgentContext",
        technical_opinion: Optional["AgentOpinion"],
        intel_opinion: Optional["AgentOpinion"],
        risk_opinion: Optional["AgentOpinion"],
    ) -> Dict[str, Any]:
        """Collect all available context data for the debate."""
        data = dict(context.data)

        if technical_opinion:
            data["technical_opinion"] = {
                "signal": technical_opinion.signal,
                "confidence": technical_opinion.confidence,
                "reasoning": technical_opinion.reasoning,
                "key_levels": technical_opinion.key_levels,
            }

        if intel_opinion:
            data["intel_opinion"] = {
                "signal": intel_opinion.signal,
                "confidence": intel_opinion.confidence,
                "reasoning": intel_opinion.reasoning,
            }

        if risk_opinion:
            data["risk_opinion"] = {
                "signal": risk_opinion.signal,
                "confidence": risk_opinion.confidence,
                "reasoning": risk_opinion.reasoning,
                "risk_flags": context.risk_flags,
            }

        return data

    def _finalize(
        self,
        state: DebateState,
        start_time: float,
        total_tokens: int,
        converged: bool,
    ) -> DebateResult:
        """Run moderation and return final result."""
        result = self.moderator.moderate(state)
        result.duration_s = round(time.time() - start_time, 2)
        result.tokens_used += total_tokens
        result.consensus_reached = converged

        # Hermes learning: save debate episode
        if self.episode_store:
            try:
                from src.agent.learning.episode_store import LearningEpisode
                ep = LearningEpisode(
                    stock_code=state.stock_code,
                    stock_name=state.stock_name,
                    date="",
                    market_features={
                        "technical_opinion": {
                            "signal": state.technical_opinion.signal if state.technical_opinion else "",
                        } if state.technical_opinion else {},
                    },
                    debate_signal=result.final_signal,
                    debate_confidence=result.final_confidence,
                    debate_rounds=result.rounds_completed,
                    debate_converged=converged,
                    final_signal=result.final_signal,
                    final_confidence=result.final_confidence,
                )
                self.episode_store.save(ep)
            except Exception as exc:
                logger.warning("[DebateArena] failed to save episode: %s", exc)

        # Hermes learning: track debate performance
        if self.debate_tracker and state.rounds:
            try:
                r1 = state.rounds[0]
                if r1.bull_argument and r1.bear_argument:
                    self.debate_tracker.track_debate(
                        stock_code=state.stock_code,
                        date="",
                        bull_signal=r1.bull_argument.signal,
                        bull_confidence=r1.bull_argument.confidence,
                        bear_signal=r1.bear_argument.signal,
                        bear_confidence=r1.bear_argument.confidence,
                        final_signal=result.final_signal,
                        final_confidence=result.final_confidence,
                    )
            except Exception as exc:
                logger.warning("[DebateArena] failed to track debate: %s", exc)

        return result

    # -----------------------------------------------------------------
    # Hermes learning helpers
    # -----------------------------------------------------------------

    def _retrieve_relevant_skills(
        self,
        context_data: Dict[str, Any],
    ) -> str:
        """Retrieve learned skills relevant to current market conditions."""
        if not self.skill_memory:
            return ""

        # Build query from available context
        query_parts = []
        tech = context_data.get("technical_opinion", {})
        if tech:
            if tech.get("signal"):
                query_parts.append(tech["signal"])
            if tech.get("reasoning"):
                query_parts.append(tech["reasoning"][:200])

        intel = context_data.get("intel_opinion", {})
        if intel and intel.get("reasoning"):
            query_parts.append(intel["reasoning"][:200])

        risk = context_data.get("risk_opinion", {})
        if risk and risk.get("reasoning"):
            query_parts.append(f"risk: {risk['reasoning'][:200]}")

        if not query_parts:
            return ""

        query = " ".join(query_parts)
        skills = self.skill_memory.search(query, top_k=3)
        if not skills:
            return ""

        parts = ["\n## Learned Skills from Past Analysis"]
        parts.append("The following are lessons learned from past prediction errors. ")
        parts.append("Consider these when forming your arguments.\n")
        for i, skill in enumerate(skills, 1):
            parts.append(f"### Skill {i}: {skill.skill_name}")
            parts.append(f"**Description**: {skill.description}")
            parts.append(f"**Trigger**: {skill.trigger_condition}")
            parts.append(f"**Action**: {skill.action}")
            parts.append("")

        return "\n".join(parts)
