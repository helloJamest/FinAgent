# -*- coding: utf-8 -*-
"""
LessonBank — persistent store for agent reflection lessons.

Stores lessons learned from past prediction errors, organised by category
and stock. Future analyses can query the lesson bank for relevant context
to inject into agent prompts.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lesson categories for classification
CATEGORIES = {
    "technical": "Technical analysis error (MA, pattern, indicator misread)",
    "capital_flow": "Capital flow misjudgement (north-bound, volume, institutional)",
    "sentiment": "Sentiment/news misjudgement (overlooked catalyst or risk)",
    "risk": "Risk management failure (ignored warning, poor stop-loss)",
    "timing": "Timing error (too early/late entry or exit)",
    "macro": "Macro environment misread (policy, rate, sector rotation)",
    "overconfidence": "Overconfidence in weak signal",
    "other": "Uncategorised lesson",
}


@dataclass
class Lesson:
    """A single lesson learned from a prediction error."""
    id: str = ""
    stock_code: str = ""
    date: str = ""
    prediction: str = ""
    actual: str = ""
    root_cause: str = ""
    category: str = "other"
    description: str = ""
    # What should be done differently next time
    corrective_action: str = ""
    # Severity: 1-5 (5 = most impactful)
    severity: int = 3
    # Whether this lesson has been applied to prompts
    applied: bool = False
    created_at: float = field(default_factory=time.time)
    last_applied_at: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"{self.stock_code}_{self.date}_{int(time.time())}"
        if self.category not in CATEGORIES:
            self.category = "other"
        self.severity = max(1, min(5, int(self.severity)))


class LessonBank:
    """Persistent lesson bank for agent self-improvement.

    Usage::

        bank = LessonBank(max_lessons=100)
        bank.save(Lesson(...))
        lessons = bank.query("600519", category="technical")
        context = bank.build_prompt_context(lessons)
    """

    def __init__(self, max_lessons: int = 100, storage_path: Optional[str] = None):
        self.max_lessons = max_lessons
        if storage_path is None:
            storage_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "data",
                "lesson_bank.json",
            )
        self.storage_path = storage_path
        self._lessons: List[Lesson] = []
        self._load()

    def save(self, lesson: Lesson) -> None:
        """Save a lesson, enforcing max size (oldest removed first)."""
        # Check for duplicates
        for existing in self._lessons:
            if existing.id == lesson.id:
                logger.debug("[LessonBank] lesson %s already exists, skipping", lesson.id)
                return

        self._lessons.append(lesson)

        # Enforce max size — remove oldest
        if len(self._lessons) > self.max_lessons:
            self._lessons.sort(key=lambda l: l.created_at)
            removed = self._lessons[: len(self._lessons) - self.max_lessons]
            self._lessons = self._lessons[-self.max_lessons :]
            if removed:
                logger.debug("[LessonBank] removed %d old lessons (max=%d)", len(removed), self.max_lessons)

        self._save()

    def save_many(self, lessons: List[Lesson]) -> int:
        """Save multiple lessons. Returns count saved."""
        count = 0
        for lesson in lessons:
            # Check duplicates
            if not any(l.id == lesson.id for l in self._lessons):
                self._lessons.append(lesson)
                count += 1
        # Enforce max size
        if len(self._lessons) > self.max_lessons:
            self._lessons.sort(key=lambda l: l.created_at)
            self._lessons = self._lessons[-self.max_lessons:]
        self._save()
        return count

    def query(
        self,
        stock_code: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Lesson]:
        """Query lessons by stock code and/or category."""
        results = self._lessons
        if stock_code:
            results = [l for l in results if l.stock_code == stock_code]
        if category:
            results = [l for l in results if l.category == category]
        # Sort by severity (high first) then recency
        results.sort(key=lambda l: (l.severity, l.created_at), reverse=True)
        return results[:limit]

    def get_all(self) -> List[Lesson]:
        """Return all lessons sorted by recency."""
        return sorted(self._lessons, key=lambda l: l.created_at, reverse=True)

    def get_stats(self) -> Dict[str, Any]:
        """Return summary statistics about stored lessons."""
        if not self._lessons:
            return {"total": 0, "by_category": {}, "by_severity": {}}

        by_category: Dict[str, int] = {}
        by_severity: Dict[int, int] = {}
        for lesson in self._lessons:
            by_category[lesson.category] = by_category.get(lesson.category, 0) + 1
            by_severity[lesson.severity] = by_severity.get(lesson.severity, 0) + 1

        return {
            "total": len(self._lessons),
            "by_category": by_category,
            "by_severity": by_severity,
            "applied_count": sum(1 for l in self._lessons if l.applied),
        }

    def build_prompt_context(self, lessons: List[Lesson]) -> str:
        """Build a text context block for injecting into agent prompts."""
        if not lessons:
            return ""

        lines = ["[Lessons from Past Analysis]"]
        for lesson in lessons:
            lines.append(
                f"- {lesson.date} [{lesson.category}] {lesson.root_cause}"
            )
            if lesson.corrective_action:
                lines.append(f"  -> Corrective action: {lesson.corrective_action}")
        lines.append("Use these lessons to avoid repeating past mistakes. Do not mention them explicitly in the output.")
        return "\n".join(lines)

    def mark_applied(self, lesson_id: str) -> bool:
        """Mark a lesson as applied to analysis prompts."""
        for lesson in self._lessons:
            if lesson.id == lesson_id:
                lesson.applied = True
                lesson.last_applied_at = time.time()
                self._save()
                return True
        return False

    # -----------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------

    def _load(self) -> None:
        """Load lessons from storage."""
        path = Path(self.storage_path)
        if not path.exists():
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                self._lessons = []
                for item in data:
                    try:
                        lesson = Lesson(**item)
                        self._lessons.append(lesson)
                    except (TypeError, KeyError):
                        continue

            logger.info("[LessonBank] loaded %d lessons from %s", len(self._lessons), self.storage_path)
        except Exception as exc:
            logger.warning("[LessonBank] failed to load lessons: %s", exc)
            self._lessons = []

    def _save(self) -> None:
        """Save lessons to storage."""
        try:
            path = Path(self.storage_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump([asdict(l) for l in self._lessons], f, ensure_ascii=False, indent=2)
            logger.debug("[LessonBank] saved %d lessons to %s", len(self._lessons), self.storage_path)
        except Exception as exc:
            logger.warning("[LessonBank] failed to save lessons: %s", exc)
