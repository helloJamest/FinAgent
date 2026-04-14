# -*- coding: utf-8 -*-
"""
ReflectionEngine — main controller for agent self-reflection.

Orchestrates the reflection lifecycle:
1. Triggers reflection based on configured schedule/threshold
2. Fetches past predictions with actual outcomes
3. Runs SelfCritic to diagnose errors
4. Stores lessons in LessonBank
5. Updates strategies via StrategyUpdater

Usage::

    engine = ReflectionEngine(llm_adapter, config=config)
    # Manual trigger
    engine.reflect(stock_code="600519", days=7)
    # Get prompt injections for a stock
    injections = engine.get_prompt_injections("600519")
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from src.agent.reflection.lesson_bank import Lesson, LessonBank
from src.agent.reflection.self_critic import ReflectionLesson, SelfCritic
from src.agent.reflection.strategy_updater import StrategyMutation, StrategyUpdater

if TYPE_CHECKING:
    from src.agent.llm_adapter import LLMToolAdapter
    from src.agent.learning import TradingSkillMemory, SkillExtractor, EpisodeStore

logger = logging.getLogger(__name__)


class ReflectionEngine:
    """Main controller for agent self-reflection."""

    def __init__(
        self,
        llm_adapter: "LLMToolAdapter",
        config=None,
    ):
        self.llm_adapter = llm_adapter
        self.config = config

        # Load config values
        self.enabled = False
        self.trigger = "daily"
        self.lookback_days = 7
        self.auto_apply = False
        self.max_lessons = 100
        self._load_config()

        # Sub-components
        self.lesson_bank = LessonBank(max_lessons=self.max_lessons)
        self.self_critic = SelfCritic(llm_adapter)
        self.strategy_updater = StrategyUpdater(lesson_bank=self.lesson_bank)

        # Hermes learning components (optional, injected from factory)
        self.skill_extractor: Optional["SkillExtractor"] = None
        self.skill_memory: Optional["TradingSkillMemory"] = None
        self.episode_store: Optional["EpisodeStore"] = None

        # Tracking
        self._last_reflection_time: Optional[float] = None

    def reflect(
        self,
        stock_code: Optional[str] = None,
        days: Optional[int] = None,
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        """Run a reflection cycle.

        Args:
            stock_code: If specified, reflect on this stock only.
                       If None, reflect on all stocks.
            days: Override lookback days for this run.
            use_llm: Whether to use LLM-based critique (falls back to
                    heuristic if False).

        Returns:
            Summary dict with keys:
            - predictions_analyzed: count
            - lessons_found: count
            - lessons_saved: count
            - mutations_applied: count
            - duration_s: float
        """
        t0 = time.time()
        lookback = days or self.lookback_days

        logger.info(
            "[ReflectionEngine] starting reflection: stock=%s, days=%d, llm=%s",
            stock_code, lookback, use_llm,
        )

        # Fetch predictions with actuals
        predictions = self._fetch_predictions_with_actuals(stock_code, lookback)
        if not predictions:
            logger.info("[ReflectionEngine] no predictions to reflect")
            return {
                "predictions_analyzed": 0,
                "lessons_found": 0,
                "lessons_saved": 0,
                "mutations_applied": 0,
                "duration_s": round(time.time() - t0, 2),
            }

        # Run critique
        if use_llm:
            lessons = self.self_critic.criticize(predictions)
        else:
            lessons = self.self_critic.heuristic_critique(predictions)

        # Convert to storable lessons
        storable = [lesson.to_lesson() for lesson in lessons]

        # Save to lesson bank
        saved = self.lesson_bank.save_many(storable)

        # Apply lessons to strategy
        mutations: List[StrategyMutation] = []
        if self.auto_apply and storable:
            mutations = self.strategy_updater.apply_lessons(storable)

        # Hermes learning: extract skills and store in vector memory
        if self.skill_extractor and self.skill_memory and storable:
            for lesson in storable:
                try:
                    skill = self.skill_extractor.extract_skill(lesson)
                    if skill:
                        text = f"{skill.skill_name} {skill.description} {skill.trigger_condition} {skill.action}"
                        self.skill_memory.add_skill(skill, text)
                except Exception as exc:
                    logger.warning("[ReflectionEngine] skill extraction failed: %s", exc)

        self._last_reflection_time = time.time()

        result = {
            "predictions_analyzed": len(predictions),
            "lessons_found": len(lessons),
            "lessons_saved": saved,
            "mutations_applied": len(mutations),
            "duration_s": round(time.time() - t0, 2),
        }

        logger.info("[ReflectionEngine] reflection complete: %s", result)
        return result

    def get_prompt_injections(self, stock_code: str = "") -> str:
        """Get active prompt injections for agent prompts."""
        return self.strategy_updater.get_prompt_injections(stock_code)

    def get_stats(self) -> Dict[str, Any]:
        """Get reflection engine statistics."""
        return {
            "enabled": self.enabled,
            "trigger": self.trigger,
            "lookback_days": self.lookback_days,
            "auto_apply": self.auto_apply,
            "last_reflection": self._last_reflection_time,
            "lesson_bank": self.lesson_bank.get_stats(),
            "strategy_mutations": self.strategy_updater.get_stats(),
        }

    def should_trigger(self) -> bool:
        """Check if reflection should be triggered based on schedule."""
        if not self.enabled:
            return False

        now = time.time()

        if self.trigger == "daily":
            # Trigger if last reflection was > 20 hours ago
            if self._last_reflection_time is None:
                return True
            return (now - self._last_reflection_time) > 20 * 3600

        elif self.trigger == "weekly":
            if self._last_reflection_time is None:
                return True
            return (now - self._last_reflection_time) > 6 * 24 * 3600

        elif self.trigger == "threshold":
            # Trigger based on number of unaudited predictions
            # This would require checking the backtest service for new results
            return self._check_threshold_trigger()

        return False

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _load_config(self) -> None:
        """Load reflection settings from config."""
        if self.config is None:
            return

        self.enabled = getattr(self.config, "reflection_enabled", False)
        self.trigger = getattr(self.config, "reflection_trigger", "daily")
        self.lookback_days = int(getattr(self.config, "reflection_lookback_days", 7))
        self.auto_apply = getattr(self.config, "reflection_auto_apply", False)
        self.max_lessons = int(getattr(self.config, "reflection_max_lessons", 100))

    def _fetch_predictions_with_actuals(
        self,
        stock_code: Optional[str],
        days: int,
    ) -> List[Dict[str, Any]]:
        """Fetch past predictions with their actual outcomes from backtest data."""
        try:
            from src.services.backtest_service import BacktestService

            service = BacktestService()
            evaluations = service.get_recent_evaluations(
                code=stock_code,
                limit=100,
            )

            predictions = []
            cutoff = datetime.now() - timedelta(days=days)

            for item in evaluations.get("items", []):
                # Filter by date
                analysis_date_str = item.get("analysis_date")
                if analysis_date_str:
                    try:
                        analysis_date = datetime.fromisoformat(analysis_date_str)
                        if analysis_date < cutoff:
                            continue
                    except ValueError:
                        pass

                # Skip if we can't determine correctness
                direction_correct = item.get("direction_correct")
                if direction_correct is None:
                    continue

                predictions.append({
                    "stock_code": item.get("code", ""),
                    "date": analysis_date_str or "",
                    "prediction": item.get("operation_advice", ""),
                    "confidence": 0.5,  # Default since backtest doesn't store confidence
                    "actual_return": item.get("stock_return_pct", 0.0) or 0.0,
                    "actual_movement": item.get("actual_movement", ""),
                    "direction_correct": bool(direction_correct),
                    "reasoning": "",
                })

            return predictions

        except Exception as exc:
            logger.warning("[ReflectionEngine] failed to fetch predictions: %s", exc)
            return []

    def _check_threshold_trigger(self) -> bool:
        """Check if threshold-based reflection should trigger."""
        try:
            from src.services.backtest_service import BacktestService
            service = BacktestService()

            # Check recent unaudited evaluations
            evaluations = service.get_recent_evaluations(code=None, limit=50)
            items = evaluations.get("items", [])

            # Count predictions that haven't been reflected on
            unaudited = 0
            if self._last_reflection_time:
                cutoff = datetime.fromtimestamp(self._last_reflection_time)
                for item in items:
                    date_str = item.get("evaluated_at", "")
                    if date_str:
                        try:
                            eval_time = datetime.fromisoformat(date_str)
                            if eval_time > cutoff:
                                unaudited += 1
                        except ValueError:
                            pass
            else:
                unaudited = len(items)

            # Trigger if more than 10 unaudited predictions
            return unaudited > 10

        except Exception as exc:
            logger.warning("[ReflectionEngine] threshold check failed: %s", exc)
            return False
