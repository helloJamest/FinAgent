# -*- coding: utf-8 -*-
"""EpisodeStore — Episodic memory for individual trade analysis cycles.

Stores complete "episodes": input features -> debate state -> decision -> actual outcome.
Used as the data source for ReflectionEngine and the learning loop.
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

_DEFAULT_STORE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
)


@dataclass
class LearningEpisode:
    """A single episode: from analysis through decision to outcome."""

    episode_id: str = ""
    stock_code: str = ""
    stock_name: str = ""
    date: str = ""
    # Input features at decision time
    market_features: Dict[str, Any] = field(default_factory=dict)
    # Debate state summary
    debate_signal: str = ""
    debate_confidence: float = 0.5
    debate_rounds: int = 0
    debate_converged: bool = False
    # Final decision
    final_signal: str = ""
    final_confidence: float = 0.5
    # Outcome (filled in later by backtest eval)
    actual_return: float = 0.0
    actual_movement: str = ""
    direction_correct: Optional[bool] = None
    # Timing
    created_at: float = field(default_factory=time.time)
    evaluated_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearningEpisode":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class EpisodeStore:
    """Persistent store for learning episodes.

    Usage::

        store = EpisodeStore()
        store.save(episode)
        episodes = store.get_episodes("600519", limit=5)
    """

    def __init__(self, persist_dir: str = _DEFAULT_STORE_DIR, max_episodes: int = 1000):
        self.persist_dir = persist_dir
        self.max_episodes = max_episodes
        self._episodes: List[LearningEpisode] = []
        self._load()

    def save(self, episode: LearningEpisode) -> None:
        """Save an episode, enforcing max size (oldest removed first)."""
        if not episode.episode_id:
            episode.episode_id = f"ep_{int(time.time() * 1000)}"

        # Check for duplicates
        for existing in self._episodes:
            if existing.episode_id == episode.episode_id:
                return

        self._episodes.append(episode)

        if len(self._episodes) > self.max_episodes:
            self._episodes.sort(key=lambda e: e.created_at)
            self._episodes = self._episodes[-self.max_episodes:]

        self._save()

    def update_outcome(
        self,
        stock_code: str,
        actual_return: float,
        actual_movement: str = "",
    ) -> int:
        """Fill in actual outcomes for recent unaudited episodes."""
        count = 0
        for ep in self._episodes:
            if ep.stock_code == stock_code and ep.direction_correct is None and ep.actual_return == 0:
                ep.actual_return = actual_return
                ep.actual_movement = actual_movement
                ep.evaluated_at = time.time()
                if actual_return > 1 and ep.final_signal in ("buy",):
                    ep.direction_correct = True
                elif actual_return < -1 and ep.final_signal in ("sell",):
                    ep.direction_correct = True
                elif abs(actual_return) <= 1 and ep.final_signal == "hold":
                    ep.direction_correct = True
                else:
                    ep.direction_correct = False
                count += 1
        if count > 0:
            self._save()
        return count

    def get_episodes(
        self,
        stock_code: Optional[str] = None,
        limit: int = 100,
    ) -> List[LearningEpisode]:
        """Get recent episodes, optionally filtered by stock."""
        results = self._episodes
        if stock_code:
            results = [e for e in results if e.stock_code == stock_code]
        return sorted(results, key=lambda e: e.created_at, reverse=True)[:limit]

    def get_unaudited(self) -> List[LearningEpisode]:
        """Get episodes without actual outcomes."""
        return [e for e in self._episodes if e.direction_correct is None]

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._episodes)
        evaluated = sum(1 for e in self._episodes if e.direction_correct is not None)
        correct = sum(1 for e in self._episodes if e.direction_correct is True)

        return {
            "total_episodes": total,
            "evaluated": evaluated,
            "unaudited": total - evaluated,
            "accuracy": correct / evaluated if evaluated > 0 else None,
            "persist_dir": self.persist_dir,
        }

    # -----------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------

    def _load(self) -> None:
        path = self._path()
        if not path.exists():
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                self._episodes = []
                for item in data:
                    try:
                        ep = LearningEpisode.from_dict(item)
                        self._episodes.append(ep)
                    except (TypeError, KeyError):
                        continue

            logger.info(
                "[EpisodeStore] loaded %d episodes from %s",
                len(self._episodes), path,
            )
        except Exception as exc:
            logger.warning("[EpisodeStore] failed to load episodes: %s", exc)

    def _save(self) -> None:
        path = self._path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    [e.to_dict() for e in self._episodes],
                    f, ensure_ascii=False, indent=2,
                )
            logger.debug(
                "[EpisodeStore] saved %d episodes to %s",
                len(self._episodes), path,
            )
        except Exception as exc:
            logger.warning("[EpisodeStore] failed to save episodes: %s", exc)

    def _path(self) -> Path:
        return Path(self.persist_dir) / "learning_episodes.json"
