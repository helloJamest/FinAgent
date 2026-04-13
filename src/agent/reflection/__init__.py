# -*- coding: utf-8 -*-
"""Reflection module — self-improvement engine for agent learning."""

from src.agent.reflection.lesson_bank import Lesson, LessonBank
from src.agent.reflection.reflection_engine import ReflectionEngine
from src.agent.reflection.self_critic import ReflectionLesson, SelfCritic
from src.agent.reflection.strategy_updater import StrategyMutation, StrategyUpdater

__all__ = [
    "Lesson",
    "LessonBank",
    "ReflectionEngine",
    "ReflectionLesson",
    "SelfCritic",
    "StrategyMutation",
    "StrategyUpdater",
]
