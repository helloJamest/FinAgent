# -*- coding: utf-8 -*-
"""SkillExtractor — LLM-powered skill abstraction from lessons.

Converts reflection lessons and debate outcomes into structured,
reusable trading skills that can be stored and retrieved by
TradingSkillMemory.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from src.agent.learning.skill_memory import TradingSkill
from src.agent.runner import try_parse_json

if TYPE_CHECKING:
    from src.agent.llm_adapter import LLMToolAdapter
    from src.agent.reflection.lesson_bank import Lesson
    from src.agent.debate.debate_protocols import DebateResult

logger = logging.getLogger(__name__)

_SKILL_EXTRACT_SYSTEM_PROMPT = """\
You are a **Skill Abstraction** module in a stock-analysis AI system.

Your task: convert a prediction error lesson into a structured, reusable
trading skill that the system can apply to future decisions.

## Input
You will receive a lesson describing a prediction error, including:
- Stock code, date, predicted signal vs actual outcome
- Root cause of the error
- Category of the error (technical, sentiment, risk, etc.)
- Suggested corrective action

## What to Extract
1. **Skill name** — a concise, descriptive identifier (snake_case English)
2. **Description** — one sentence summarizing the pattern
3. **Trigger condition** — specific market conditions under which this skill applies
4. **Action** — what the agent should do when the trigger is met
5. **Category** — one of: technical, sentiment, risk, capital_flow, timing, macro, other

## Output Format
Return **only** a valid JSON object:
{
  "skill_name": "avoid_technical_divergence_blindspot",
  "description": "When MA alignment and MACD diverge, the dominant signal is often wrong",
  "trigger_condition": "MA bullish but MACD bearish divergence, or vice versa",
  "action": "Reduce confidence by 30%% and flag as mixed signal; prefer hold unless both converge",
  "category": "technical"
}

Be concise. Every skill should be actionable.
"""


@dataclass
class ExtractedSkill:
    """A skill extracted by the LLM from a lesson."""
    skill_name: str = ""
    description: str = ""
    trigger_condition: str = ""
    action: str = ""
    category: str = "other"

    def to_trading_skill(self, source: str = "") -> TradingSkill:
        """Convert to a TradingSkill instance."""
        skill = TradingSkill(
            skill_id=f"skill_{int(time.time() * 1000)}",
            skill_name=self.skill_name,
            description=self.description,
            trigger_condition=self.trigger_condition,
            action=self.action,
            category=self.category,
            confidence=0.7,
        )
        return skill


class SkillExtractor:
    """LLM-powered extraction of structured skills from lessons."""

    VALID_CATEGORIES = {"technical", "sentiment", "risk", "capital_flow", "timing", "macro", "other"}

    def __init__(self, llm_adapter: "LLMToolAdapter"):
        self.llm_adapter = llm_adapter

    def extract_skill(self, lesson: "Lesson") -> Optional[TradingSkill]:
        """Extract a structured trading skill from a reflection lesson."""
        user_message = self._build_extract_prompt(lesson)

        try:
            messages = [
                {"role": "system", "content": _SKILL_EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]

            response = self.llm_adapter.chat(
                messages=messages,
                temperature=0.3,
                max_tokens=1024,
            )

            content = response.get("content", "") if isinstance(response, dict) else ""
            return self._parse_skill(content)

        except Exception as exc:
            logger.error("[SkillExtractor] extraction failed: %s", exc)
            return None

    def extract_debate_skill(
        self,
        debate_result: "DebateResult",
        actual_return: float,
    ) -> Optional[TradingSkill]:
        """Extract skill about which debate side was more accurate."""
        user_message = self._build_debate_skill_prompt(debate_result, actual_return)

        try:
            messages = [
                {"role": "system", "content": _SKILL_EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]

            response = self.llm_adapter.chat(
                messages=messages,
                temperature=0.3,
                max_tokens=1024,
            )

            content = response.get("content", "") if isinstance(response, dict) else ""
            return self._parse_skill(content)

        except Exception as exc:
            logger.error("[SkillExtractor] debate skill extraction failed: %s", exc)
            return None

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _build_extract_prompt(lesson: "Lesson") -> str:
        lines = [
            f"## Lesson to convert into a trading skill",
            f"- Stock: {lesson.stock_code} on {lesson.date}",
            f"- Prediction: {lesson.prediction} (actual: {lesson.actual})",
            f"- Root cause: {lesson.root_cause}",
            f"- Category: {lesson.category}",
            f"- Description: {lesson.description}",
            f"- Corrective action: {lesson.corrective_action}",
            f"- Severity: {lesson.severity}/5",
            "",
            "Convert this into a reusable trading skill.",
        ]
        return "\n".join(lines)

    @staticmethod
    def _build_debate_skill_prompt(
        debate_result: "DebateResult",
        actual_return: float,
    ) -> str:
        lines = [
            f"## Debate outcome to convert into a trading skill",
            f"- Final signal: {debate_result.final_signal}",
            f"- Final confidence: {debate_result.final_confidence:.2f}",
            f"- Actual return: {actual_return:.1f}%",
            f"- Consensus reached: {debate_result.consensus_reached}",
            f"- Rounds: {debate_result.rounds_completed}",
            "",
        ]

        # Add round-level signals
        if debate_result.all_rounds:
            for i, r in enumerate(debate_result.all_rounds, 1):
                lines.append(f"### Round {i}")
                if r.bull_argument:
                    lines.append(
                        f"  Bull: {r.bull_argument.signal} (conf={r.bull_argument.confidence:.2f})"
                    )
                if r.bear_argument:
                    lines.append(
                        f"  Bear: {r.bear_argument.signal} (conf={r.bear_argument.confidence:.2f})"
                    )

        actual_signal = "buy" if actual_return > 1 else ("sell" if actual_return < -1 else "hold")
        lines.append("")
        lines.append(f"The actual outcome suggests a '{actual_signal}' signal.")
        lines.append("Extract a skill about what the debate got right or wrong.")
        return "\n".join(lines)

    def _parse_skill(self, text: str) -> Optional[TradingSkill]:
        parsed = try_parse_json(text)
        if parsed is None:
            logger.warning("[SkillExtractor] failed to parse skill JSON")
            return None

        skill_name = str(parsed.get("skill_name", "")).strip()
        if not skill_name:
            logger.warning("[SkillExtractor] extracted skill has no name")
            return None

        category = str(parsed.get("category", "other")).strip().lower()
        if category not in self.VALID_CATEGORIES:
            category = "other"

        return TradingSkill(
            skill_id=f"skill_{int(time.time() * 1000)}",
            skill_name=skill_name,
            description=str(parsed.get("description", "")),
            trigger_condition=str(parsed.get("trigger_condition", "")),
            action=str(parsed.get("action", "")),
            category=category,
            confidence=0.7,
        )
