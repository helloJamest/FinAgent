# -*- coding: utf-8 -*-
"""
SelfCritic — introspective analysis module for prediction error diagnosis.

Compares past predictions against actual outcomes, identifies root causes
of errors, and classifies lessons for storage in the lesson bank.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from src.agent.reflection.lesson_bank import CATEGORIES, Lesson

if TYPE_CHECKING:
    from src.agent.llm_adapter import LLMToolAdapter

logger = logging.getLogger(__name__)

# System prompt for the LLM-powered self-critic.
_SELF_CRITIC_SYSTEM_PROMPT = """\
You are a **Self-Critic** module in a stock-analysis AI system.

Your task: review past predictions against actual outcomes, identify \
why each prediction was wrong (or right but for the wrong reason), and \
produce actionable lessons.

## Input Format
You will receive a list of past predictions with:
- Stock code, prediction date, predicted signal, confidence
- Actual price movement and return over the evaluation window
- Whether the prediction direction was correct

## What to Analyze
1. **Root cause** — why was this prediction wrong? Be specific:
   - Did the agent ignore a technical warning sign?
   - Was there a capital flow mismatch (e.g., north-bound outflow)?
   - Did sentiment/news contradict the technical signal?
   - Was confidence misplaced given the evidence?

2. **Category** — classify into one of:
   - `technical`: MA/pattern/indicator misread
   - `capital_flow`: volume/institutional flow misjudgement
   - `sentiment`: news/sentiment misread
   - `risk`: risk management failure
   - `timing`: entry/exit timing error
   - `macro`: macro environment misread
   - `overconfidence`: high confidence on weak evidence
   - `other`: unclassifiable

3. **Corrective action** — what should the agent do differently next time?

## Output Format
Return **only** a valid JSON array:
[
  {
    "stock_code": "600519",
    "date": "2026-04-10",
    "prediction": "buy",
    "actual": "sell",
    "root_cause": "Ignored declining MACD divergence despite bullish MA alignment",
    "category": "technical",
    "description": "Technical agent over-weighted MA alignment while MACD showed bearish divergence",
    "corrective_action": "When MA and MACD diverge, reduce confidence and flag as mixed signal",
    "severity": 3
  }
]

Be concise, honest, and specific. Every lesson should be actionable.
"""


@dataclass
class ReflectionLesson:
    """A lesson produced by the SelfCritic."""
    stock_code: str = ""
    date: str = ""
    prediction: str = ""
    actual: str = ""
    root_cause: str = ""
    category: str = "other"
    description: str = ""
    corrective_action: str = ""
    severity: int = 3
    confidence_at_time: float = 0.0

    def to_lesson(self) -> Lesson:
        """Convert to a storable Lesson."""
        return Lesson(
            stock_code=self.stock_code,
            date=self.date,
            prediction=self.prediction,
            actual=self.actual,
            root_cause=self.root_cause,
            category=self.category,
            description=self.description,
            corrective_action=self.corrective_action,
            severity=self.severity,
        )


class SelfCritic:
    """LLM-powered introspective analysis of prediction errors."""

    def __init__(self, llm_adapter: "LLMToolAdapter"):
        self.llm_adapter = llm_adapter

    def criticize(
        self,
        predictions: List[Dict[str, Any]],
    ) -> List[ReflectionLesson]:
        """Analyze a list of predictions vs actuals and produce lessons.

        Each prediction dict should have:
        - stock_code, date, prediction (signal), confidence
        - actual_return, actual_movement (up/down/flat)
        - direction_correct (bool)
        """
        if not predictions:
            return []

        user_message = self._build_critique_prompt(predictions)

        try:
            messages = [
                {"role": "system", "content": _SELF_CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]

            response = self.llm_adapter.chat(
                messages=messages,
                temperature=0.3,
                max_tokens=4096,
            )

            content = response.get("content", "") if isinstance(response, dict) else ""
            lessons = self._parse_lessons(content)

            if lessons:
                logger.info(
                    "[SelfCritic] produced %d lessons from %d predictions",
                    len(lessons), len(predictions),
                )
            return lessons

        except Exception as exc:
            logger.error("[SelfCritic] critique failed: %s", exc)
            return []

    # -----------------------------------------------------------------
    # Heuristic (non-LLM) fallback for simple cases
    # -----------------------------------------------------------------

    def heuristic_critique(
        self,
        predictions: List[Dict[str, Any]],
    ) -> List[ReflectionLesson]:
        """Rule-based heuristic analysis when LLM is unavailable."""
        lessons = []

        for pred in predictions:
            direction_correct = pred.get("direction_correct", True)
            if direction_correct:
                continue  # Only analyze wrong predictions

            stock_code = pred.get("stock_code", "")
            date = pred.get("date", "")
            prediction = pred.get("prediction", "hold")
            confidence = pred.get("confidence", 0.5)
            actual_return = pred.get("actual_return", 0.0)

            # Determine category based on error pattern
            if abs(actual_return) > 5:
                category = "risk"
                root_cause = f"Failed to anticipate large move ({actual_return:.1f}%)"
            elif confidence > 0.7 and not direction_correct:
                category = "overconfidence"
                root_cause = f"High confidence ({confidence:.0%}) but prediction was wrong"
            else:
                category = "technical"
                root_cause = "Technical signal was misleading"

            actual_signal = "buy" if actual_return > 1 else ("sell" if actual_return < -1 else "hold")

            lesson = ReflectionLesson(
                stock_code=stock_code,
                date=date,
                prediction=prediction,
                actual=actual_signal,
                root_cause=root_cause,
                category=category,
                description=f"Predicted {prediction} with {confidence:.0%} confidence; actual return was {actual_return:.1f}%",
                corrective_action=f"Review {category} analysis methodology",
                severity=min(5, int(abs(actual_return) / 2) + 1),
                confidence_at_time=confidence,
            )
            lessons.append(lesson)

        return lessons

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _build_critique_prompt(predictions: List[Dict[str, Any]]) -> str:
        """Build the critique prompt from prediction data."""
        lines = [f"# Analyzing {len(predictions)} past predictions"]
        lines.append("")

        for i, pred in enumerate(predictions, 1):
            direction_correct = pred.get("direction_correct", True)
            actual_return = pred.get("actual_return", 0.0)
            confidence = pred.get("confidence", 0.5)

            lines.append(f"## #{i}: {pred.get('stock_code', '?')} on {pred.get('date', '?')}")
            lines.append(f"- Predicted: {pred.get('prediction', 'hold')} (confidence: {confidence:.0%})")
            lines.append(f"- Actual return: {actual_return:.1f}%")
            lines.append(f"- Direction correct: {'Yes' if direction_correct else 'No'}")
            if pred.get("reasoning"):
                lines.append(f"- Reasoning: {pred.get('reasoning', '')[:200]}")
            lines.append("")

        lines.append("Analyze each incorrect prediction. Focus on the root causes and corrective actions.")
        return "\n".join(lines)

    @staticmethod
    def _parse_lessons(text: str) -> List[ReflectionLesson]:
        """Parse lesson JSON from LLM response."""
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            # Try to find JSON array
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                try:
                    data = json.loads(text[start:end + 1])
                except (json.JSONDecodeError, TypeError):
                    return []
            else:
                return []

        if not isinstance(data, list):
            return []

        lessons = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                lesson = ReflectionLesson(
                    stock_code=str(item.get("stock_code", "")),
                    date=str(item.get("date", "")),
                    prediction=str(item.get("prediction", "")),
                    actual=str(item.get("actual", "")),
                    root_cause=str(item.get("root_cause", "")),
                    category=str(item.get("category", "other")),
                    description=str(item.get("description", "")),
                    corrective_action=str(item.get("corrective_action", "")),
                    severity=int(item.get("severity", 3)),
                    confidence_at_time=float(item.get("confidence_at_time", 0.0)),
                )
                if lesson.category not in CATEGORIES:
                    lesson.category = "other"
                lesson.severity = max(1, min(5, lesson.severity))
                lessons.append(lesson)
            except (TypeError, ValueError):
                continue

        return lessons
