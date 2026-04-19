# -*- coding: utf-8 -*-
"""
DebateModerator — synthesises debate rounds into a final decision.

The Moderator acts as an impartial judge over the Bull/Bear debate,
considering all rounds of arguments and rebuttals plus risk flags,
and produces the final trading decision with a comprehensive dashboard.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from src.agent.debate.debate_protocols import (
    Argument,
    DebateResult,
    DebateRound,
    DebateState,
)
from src.agent.protocols import normalize_decision_signal

logger = logging.getLogger(__name__)

# Prompt for the moderator to synthesise debate rounds into a final decision.
_MODERATOR_SYSTEM_PROMPT = """\
You are an impartial **Debate Moderator** in a stock-analysis system.

A Bull Advocate and a Bear Advocate have debated a stock's prospects across \
multiple rounds. Your task is to evaluate all arguments, rebuttals, and risk \
assessments, then produce a final, balanced investment decision.

## Input You Will Receive
- The initial technical analysis opinion
- Bull and Bear initial arguments
- Rebuttals from both sides (if any)
- Risk auditor's comments
- Intel/sentiment context (if any)

## Your Job
1. **Weigh the evidence** — which side has the stronger, more evidence-backed case?
2. **Identify consensus** — what do both sides agree on?
3. **Highlight unresolved disagreements** — where do they still disagree?
4. **Apply risk flags** — any high-severity risk should cap the final signal
5. **Produce a Decision Dashboard** — concrete, actionable recommendation

## Output Format
Return **only** a valid JSON object (no markdown fences):
{
  "decision_type": "buy|hold|sell",
  "confidence": 0.0-1.0,
  "reasoning": "2-4 sentences explaining your ruling and how you weighed the debate",
  "consensus_points": ["point 1", "point 2"],
  "key_disagreements": [{"bull_says": "...", "bear_says": "..."}],
  "risk_assessment": "summary of risk considerations",
  "key_levels": {
    "support": <float>,
    "resistance": <float>,
    "stop_loss": <float>
  },
  "sentiment_score": 0-100,
  "analysis_summary": "1-2 sentence executive summary",
  "dashboard": {
    "core_conclusion": {
      "one_sentence": "<30 char conclusion>",
      "signal_type": "buy|hold|sell signal",
      "time_sensitivity": "this week|this month|long term",
      "position_advice": {"no_position": "...", "has_position": "..."}
    },
    "sniper_points": {
      "ideal_buy": <float>,
      "stop_loss": <float>,
      "take_profit": <float>
    }
  }
}

Important: ``decision_type`` must stay within the existing enum ``buy|hold|sell``.
"""


class DebateModerator:
    """Synthesises debate rounds into a final decision.

    The moderator runs an LLM call to evaluate all debate rounds and
    produce the final trading decision.
    """

    def __init__(self, llm_adapter):
        self.llm_adapter = llm_adapter

    def moderate(self, state: DebateState) -> DebateResult:
        """Run the moderation over all completed debate rounds."""
        t0 = time.time()
        tokens_used = 0

        if not state.rounds:
            return DebateResult(
                success=False,
                error="No debate rounds to moderate",
                duration_s=round(time.time() - t0, 2),
            )

        # Build the moderator prompt from debate rounds
        user_message = self._build_moderation_prompt(state)

        try:
            messages = [
                {"role": "system", "content": _MODERATOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]

            response = self.llm_adapter.call_text(
                messages=messages,
                temperature=0.3,
                max_tokens=4096,
            )

            content = response.content or ""
            tokens_used = response.usage.get("total_tokens", 0) if response.usage else 0

            # Parse JSON from response
            parsed = self._parse_json(content)
            if parsed is None:
                return DebateResult(
                    success=False,
                    error="Moderator failed to produce valid JSON",
                    duration_s=round(time.time() - t0, 2),
                    tokens_used=tokens_used,
                )

            # Build result
            decision_type = normalize_decision_signal(parsed.get("decision_type", "hold"))
            confidence = float(parsed.get("confidence", 0.5))
            reasoning = parsed.get("reasoning", "")

            # Check for consensus
            last_round = state.rounds[-1]
            consensus = self._check_convergence(state.rounds)

            result = DebateResult(
                success=True,
                rounds_completed=len(state.rounds),
                final_signal=decision_type,
                final_confidence=confidence,
                final_reasoning=reasoning,
                consensus_reached=consensus is not None,
                convergence_round=consensus.round_number if consensus else 0,
                all_rounds=list(state.rounds),
                moderator_summary=reasoning,
                dashboard=self._build_dashboard(parsed, state),
                duration_s=round(time.time() - t0, 2),
                tokens_used=tokens_used,
            )
            return result

        except Exception as exc:
            logger.error("[DebateModerator] moderation failed: %s", exc, exc_info=True)
            return DebateResult(
                success=False,
                error=str(exc),
                duration_s=round(time.time() - t0, 2),
                tokens_used=tokens_used,
            )

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _build_moderation_prompt(self, state: DebateState) -> str:
        """Build a comprehensive prompt from all debate rounds."""
        parts = [
            f"# Stock: {state.stock_code}",
            f"Debate rounds: {len(state.rounds)}",
            "",
        ]

        # Technical opinion
        if state.technical_opinion:
            parts.append("## Technical Analysis")
            parts.append(f"Signal: {state.technical_opinion.signal}")
            parts.append(f"Confidence: {state.technical_opinion.confidence:.2f}")
            parts.append(state.technical_opinion.reasoning)
            parts.append("")

        # Intel opinion
        if state.intel_opinion:
            parts.append("## Intel / Sentiment Context")
            parts.append(state.intel_opinion.reasoning)
            parts.append("")

        # Each round
        for i, rnd in enumerate(state.rounds, 1):
            parts.append(f"## Round {i}")
            parts.append(rnd.to_summary())
            parts.append("")

        return "\n".join(parts)

    @staticmethod
    def _parse_json(text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON from LLM response."""
        # Try direct parse
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        # Try to find JSON block
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except (json.JSONDecodeError, TypeError):
                pass

        return None

    @staticmethod
    def _check_convergence(rounds: List[DebateRound]) -> Optional[DebateRound]:
        """Check if signals converged (within 1 signal level)."""
        signal_order = {"strong_sell": 0, "sell": 1, "hold": 2, "buy": 3, "strong_buy": 4}

        for rnd in rounds:
            signals = rnd.signals
            if len(signals) < 2:
                continue

            # Convert to numeric positions
            positions = []
            for sig in signals:
                pos = signal_order.get(sig)
                if pos is not None:
                    positions.append(pos)

            if not positions:
                continue

            # Check if within 1 level
            if max(positions) - min(positions) <= 1:
                return rnd

        return None

    def _build_dashboard(
        self,
        parsed: Dict[str, Any],
        state: DebateState,
    ) -> Dict[str, Any]:
        """Build a dashboard dict from the moderator's parsed output."""
        dashboard = {
            "stock_name": state.stock_name or state.stock_code,
            "sentiment_score": int(parsed.get("sentiment_score", 50)),
            "decision_type": normalize_decision_signal(parsed.get("decision_type", "hold")),
            "confidence_level": self._confidence_label(float(parsed.get("confidence", 0.5))),
            "analysis_summary": parsed.get("analysis_summary", ""),
            "risk_warning": parsed.get("risk_assessment", ""),
            "key_points": parsed.get("consensus_points", []),
            "dashboard": parsed.get("dashboard", {}),
        }

        # Fill in missing fields from parsed top-level keys
        if not dashboard.get("analysis_summary"):
            dashboard["analysis_summary"] = parsed.get("reasoning", "")

        return dashboard

    @staticmethod
    def _confidence_label(confidence: float) -> str:
        if confidence >= 0.75:
            return "高"
        if confidence >= 0.45:
            return "中"
        return "低"
