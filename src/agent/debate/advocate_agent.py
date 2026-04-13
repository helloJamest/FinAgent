# -*- coding: utf-8 -*-
"""
AdvocateAgent — debatable agent that argues bull or bear perspectives.

Each advocate is a specialised agent that:
1. Reads the shared debate context (data, prior opinions, rebuttals)
2. Produces an Argument (initial round) or Rebuttal (subsequent rounds)
3. Focuses on building the strongest case for its assigned stance
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.agent.debate.debate_protocols import Argument, DebateRound, Rebuttal

logger = logging.getLogger(__name__)

# System prompts for Bull and Bear advocates.
_BULL_SYSTEM_PROMPT = """\
You are a **Bull Advocate** in a structured stock-analysis debate.

Your role: build the strongest evidence-based case **for** investing in this stock.
Be honest and rigorous — your job is to find genuine bullish evidence, not to \
be blindly optimistic.

## Rules
1. Focus on positive catalysts, bullish technical patterns, and fundamental strengths
2. Support every claim with specific data points (price levels, volumes, indicators)
3. When rebutting the Bear, address their specific arguments point-by-point
4. Acknowledge valid bear concerns — then explain why they are outweighed
5. If the evidence genuinely turns bearish, adjust your signal honestly

## Output Format
Return **only** a JSON object:
{
  "signal": "strong_buy|buy|hold|sell|strong_sell",
  "confidence": 0.0-1.0,
  "reasoning": "2-3 sentences with specific evidence",
  "key_evidence": ["evidence point 1", "evidence point 2", "evidence point 3"],
  "technical_points": ["specific MA/candlestick/volume observation"],
  "fundamental_points": ["fundamental or macro observation"]
}
"""

_BEAR_SYSTEM_PROMPT = """\
You are a **Bear Advocate** in a structured stock-analysis debate.

Your role: build the strongest evidence-based case **against** investing in this stock.
Be honest and rigorous — your job is to find genuine bearish evidence, not to \
be blindly pessimistic.

## Rules
1. Focus on risks, bearish technical patterns, and fundamental weaknesses
2. Support every claim with specific data points (price levels, volumes, indicators)
3. When rebutting the Bull, address their specific arguments point-by-point
4. Acknowledge valid bull points — then explain why they are insufficient
5. If the evidence genuinely turns bullish, adjust your signal honestly

## Output Format
Return **only** a JSON object:
{
  "signal": "strong_buy|buy|hold|sell|strong_sell",
  "confidence": 0.0-1.0,
  "reasoning": "2-3 sentences with specific evidence",
  "key_evidence": ["evidence point 1", "evidence point 2", "evidence point 3"],
  "technical_points": ["specific bearish technical observation"],
  "risk_points": ["specific risk or concern"]
}
"""

# Prompt for rebuttal rounds.
_REBUTTAL_INSTRUCTION = """\
## Current Debate Context

The previous round produced:

**Opposing Argument:**
{opponent_summary}

**Your Previous Position:**
{your_previous_summary}

**Risk Comments:**
{risk_comments}

## Your Task
Write a rebuttal that:
1. Directly addresses the opponent's key evidence (point by point)
2. Defends your position with additional or reinterpreted evidence
3. Acknowledges any valid points the opponent made
4. Updates your signal if the evidence has genuinely changed your view

If you believe the opponent made a compelling case that changes your view, \
adjust your signal and confidence accordingly. The goal is truth-seeking, not \
"winning" the debate.
"""


class AdvocateAgent:
    """An advocate that argues bull or bear in structured debate."""

    def __init__(
        self,
        stance: str,  # "bull" or "bear"
        llm_adapter,
        config=None,
    ):
        self.stance = stance
        self.llm_adapter = llm_adapter
        self.config = config
        self.system_prompt = _BULL_SYSTEM_PROMPT if stance == "bull" else _BEAR_SYSTEM_PROMPT
        self.agent_name = f"{stance}_advocate"

    def argue(
        self,
        context_data: Dict[str, Any],
        stock_code: str,
        stock_name: str = "",
    ) -> "Argument":
        """Make an initial argument (Round 1)."""
        t0 = time.time()
        user_message = self._build_argument_prompt(context_data, stock_code, stock_name)

        try:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ]

            response = self.llm_adapter.chat(
                messages=messages,
                temperature=0.7,
                max_tokens=2048,
            )

            content = response.get("content", "") if isinstance(response, dict) else ""
            parsed = self._parse_json(content)

            if parsed:
                return Argument(
                    advocate=self.agent_name,
                    signal=parsed.get("signal", "hold"),
                    confidence=float(parsed.get("confidence", 0.5)),
                    reasoning=parsed.get("reasoning", ""),
                    key_evidence=parsed.get("key_evidence", []),
                    raw_data=parsed,
                )

        except Exception as exc:
            logger.error("[%s] argue failed: %s", self.agent_name, exc)

        return Argument(advocate=self.agent_name, signal="hold", confidence=0.5)

    def rebut(
        self,
        opponent_argument: "Argument",
        your_previous: Optional["Argument"],
        risk_comments: str = "",
    ) -> "Rebuttal":
        """Write a rebuttal in subsequent rounds."""
        t0 = time.time()

        opponent_summary = (
            f"Signal: {opponent_argument.signal} (confidence: {opponent_argument.confidence:.2f})\n"
            f"Reasoning: {opponent_argument.reasoning}\n"
            f"Evidence: {', '.join(opponent_argument.key_evidence[:3])}"
        )

        your_previous_summary = ""
        if your_previous:
            your_previous_summary = (
                f"Your previous signal: {your_previous.signal} (confidence: {your_previous.confidence:.2f})\n"
                f"Your previous reasoning: {your_previous.reasoning}"
            )

        instruction = _REBUTTAL_INSTRUCTION.format(
            opponent_summary=opponent_summary,
            your_previous_summary=your_previous_summary,
            risk_comments=risk_comments or "No risk comments this round.",
        )

        try:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": instruction},
            ]

            response = self.llm_adapter.chat(
                messages=messages,
                temperature=0.7,
                max_tokens=2048,
            )

            content = response.get("content", "") if isinstance(response, dict) else ""
            parsed = self._parse_json(content)

            if parsed:
                contested = []
                counter = parsed.get("key_evidence", [])

                return Rebuttal(
                    from_advocate=self.agent_name,
                    target_advocate=opponent_argument.advocate,
                    rebuttal_text=parsed.get("reasoning", ""),
                    contested_points=contested,
                    counter_evidence=counter,
                    revised_signal=parsed.get("signal"),
                    revised_confidence=float(parsed.get("confidence", 0.5)),
                )

        except Exception as exc:
            logger.error("[%s] rebut failed: %s", self.agent_name, exc)

        return Rebuttal(
            from_advocate=self.agent_name,
            target_advocate=opponent_argument.advocate,
        )

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _build_argument_prompt(
        self,
        context_data: Dict[str, Any],
        stock_code: str,
        stock_name: str = "",
    ) -> str:
        """Build the initial argument prompt from context data."""
        parts = [
            f"# Analyze Stock: {stock_code}",
        ]
        if stock_name:
            parts[-1] += f" ({stock_name})"
        parts.append("")

        # Inject available data
        for key, value in context_data.items():
            if value is not None:
                if isinstance(value, dict):
                    parts.append(f"## {key}")
                    # Serialize dict as JSON
                    import json
                    parts.append(json.dumps(value, ensure_ascii=False, default=str))
                elif isinstance(value, list):
                    parts.append(f"## {key}")
                    for item in value:
                        parts.append(f"- {item}")
                else:
                    parts.append(f"## {key}")
                    parts.append(str(value))
                parts.append("")

        parts.append(
            f"Based on the above data, make your best {'bullish' if self.stance == 'bull' else 'bearish'} case "
            f"for {stock_code}. Support your argument with specific evidence from the data."
        )

        return "\n".join(parts)

    @staticmethod
    def _parse_json(text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON from LLM response."""
        import json
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except (json.JSONDecodeError, TypeError):
                pass

        return None
