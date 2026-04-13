# -*- coding: utf-8 -*-
"""
StrategyUpdater — applies reflection lessons to agent analysis prompts.

When a lesson is identified by the SelfCritic, the StrategyUpdater modifies
the agent's analysis approach by updating prompt injections and tracking
strategy mutations.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.agent.reflection.lesson_bank import Lesson, LessonBank

logger = logging.getLogger(__name__)


@dataclass
class StrategyMutation:
    """A single strategy change applied based on a lesson."""
    mutation_id: str = ""
    lesson_id: str = ""
    category: str = ""
    description: str = ""
    prompt_injection: str = ""
    # Weight of this mutation (how much it should influence the prompt)
    weight: float = 1.0
    # Whether this mutation is currently active
    active: bool = True
    # How many times it has been applied
    apply_count: int = 0
    # Last time it was applied
    last_applied_at: float = field(default_factory=time.time)
    # If performance degrades, this tracks the "cost" of this mutation
    cost: float = 0.0


class StrategyUpdater:
    """Applies lessons from the LessonBank to modify agent behavior.

    Rather than rewriting source code, this updater works by injecting
    additional prompt instructions that guide the agent's analysis process.
    These injections are combined with the base prompts of Technical,
    Intel, and Decision agents at runtime.
    """

    def __init__(
        self,
        lesson_bank: Optional[LessonBank] = None,
        storage_path: Optional[str] = None,
    ):
        if lesson_bank is None:
            lesson_bank = LessonBank()
        self.lesson_bank = lesson_bank
        self.mutations: List[StrategyMutation] = []
        self._storage_path = storage_path or self._default_path()
        self._load()

    def apply_lessons(self, lessons: List[Lesson]) -> List[StrategyMutation]:
        """Convert lessons into active strategy mutations."""
        new_mutations = []

        for lesson in lessons:
            # Check if we already have a mutation for this lesson
            if any(m.lesson_id == lesson.id for m in self.mutations):
                continue

            prompt_injection = self._lesson_to_prompt(lesson)
            if not prompt_injection:
                continue

            mutation = StrategyMutation(
                mutation_id=f"mut_{lesson.id}",
                lesson_id=lesson.id,
                category=lesson.category,
                description=lesson.corrective_action,
                prompt_injection=prompt_injection,
                weight=min(1.0, lesson.severity / 5.0),
            )
            self.mutations.append(mutation)
            new_mutations.append(mutation)

            # Mark lesson as applied
            self.lesson_bank.mark_applied(lesson.id)

        if new_mutations:
            self._save()
            logger.info(
                "[StrategyUpdater] applied %d new mutations", len(new_mutations),
            )

        return new_mutations

    def get_prompt_injections(self, stock_code: str = "") -> str:
        """Get active prompt injections for a given stock context."""
        relevant = [m for m in self.mutations if m.active]

        # If stock_code specified, boost relevant mutations
        if stock_code:
            stock_lessons = self.lesson_bank.query(stock_code=stock_code, limit=20)
            stock_lesson_ids = {l.id for l in stock_lessons}
            for m in relevant:
                if m.lesson_id in stock_lesson_ids:
                    m.weight = min(1.5, m.weight * 1.5)

        if not relevant:
            return ""

        parts = []
        parts.append("## Lessons from Past Analysis (DO NOT IGNORE)")
        parts.append(
            "The following lessons are based on past prediction errors. "
            "Incorporate these learnings into your analysis without explicitly mentioning them."
        )
        parts.append("")

        # Sort by weight (most impactful first)
        relevant.sort(key=lambda m: m.weight, reverse=True)

        for mutation in relevant:
            parts.append(mutation.prompt_injection)
            parts.append("")

        return "\n".join(parts)

    def get_category_weights(self) -> Dict[str, float]:
        """Return current category-level weights based on active mutations."""
        weights: Dict[str, float] = {}
        counts: Dict[str, int] = {}

        for m in self.mutations:
            if m.active:
                weights[m.category] = weights.get(m.category, 0.0) + m.weight
                counts[m.category] = counts.get(m.category, 0) + 1

        # Average weight per category
        for cat in weights:
            if counts[cat] > 0:
                weights[cat] /= counts[cat]

        return weights

    def get_stats(self) -> Dict[str, Any]:
        """Return statistics about active mutations."""
        by_category: Dict[str, int] = {}
        total_weight = 0.0

        for m in self.mutations:
            if m.active:
                by_category[m.category] = by_category.get(m.category, 0) + 1
                total_weight += m.weight

        return {
            "total_mutations": len(self.mutations),
            "active_mutations": sum(1 for m in self.mutations if m.active),
            "by_category": by_category,
            "total_weight": round(total_weight, 2),
        }

    def deactivate(self, mutation_id: str) -> bool:
        """Deactivate a specific mutation."""
        for m in self.mutations:
            if m.mutation_id == mutation_id:
                m.active = False
                self._save()
                return True
        return False

    def deactivate_by_category(self, category: str) -> int:
        """Deactivate all mutations in a category."""
        count = 0
        for m in self.mutations:
            if m.category == category and m.active:
                m.active = False
                count += 1
        if count > 0:
            self._save()
        return count

    def reset(self) -> int:
        """Deactivate all mutations. Returns count deactivated."""
        count = sum(1 for m in self.mutations if m.active)
        for m in self.mutations:
            m.active = False
        self._save()
        return count

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _lesson_to_prompt(lesson: Lesson) -> str:
        """Convert a lesson into a prompt injection string."""
        if not lesson.corrective_action and not lesson.root_cause:
            return ""

        category_label = lesson.category.replace("_", " ").title()
        lines = [f"- [{category_label}] Lesson from {lesson.date} ({lesson.stock_code}):"]
        if lesson.root_cause:
            lines.append(f"  Past error: {lesson.root_cause}")
        if lesson.corrective_action:
            lines.append(f"  Action: {lesson.corrective_action}")
        return "\n".join(lines)

    @staticmethod
    def _default_path() -> str:
        import os
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data",
            "strategy_mutations.json",
        )

    def _load(self) -> None:
        """Load mutations from storage."""
        path = Path(self._storage_path)
        if not path.exists():
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                self.mutations = []
                for item in data:
                    try:
                        m = StrategyMutation(**item)
                        self.mutations.append(m)
                    except (TypeError, KeyError):
                        continue

            logger.info(
                "[StrategyUpdater] loaded %d mutations from %s",
                len(self.mutations), self._storage_path,
            )
        except Exception as exc:
            logger.warning("[StrategyUpdater] failed to load mutations: %s", exc)
            self.mutations = []

    def _save(self) -> None:
        """Save mutations to storage."""
        try:
            path = Path(self._storage_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump([asdict(m) for m in self.mutations], f, ensure_ascii=False, indent=2)
            logger.debug(
                "[StrategyUpdater] saved %d mutations to %s",
                len(self.mutations), self._storage_path,
            )
        except Exception as exc:
            logger.warning("[StrategyUpdater] failed to save mutations: %s", exc)
