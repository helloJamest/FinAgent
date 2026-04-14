# -*- coding: utf-8 -*-
"""DebateTracker — Tracks debate agent performance over time.

Records which side (Bull/Bear) was correct after actual results arrive,
computing per-agent accuracy and generating insights like
"Bear is more accurate when sentiment > 70".
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

_DEFAULT_TRACKER_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
)


@dataclass
class DebateRecord:
    """A single debate tracked for performance evaluation."""

    record_id: str = ""
    stock_code: str = ""
    date: str = ""
    bull_signal: str = ""
    bull_confidence: float = 0.5
    bear_signal: str = ""
    bear_confidence: float = 0.5
    final_signal: str = ""
    final_confidence: float = 0.5
    actual_return: float = 0.0
    bull_correct: Optional[bool] = None
    bear_correct: Optional[bool] = None
    tracked_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DebateRecord":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class DebateTracker:
    """Track and analyze debate performance over time.

    Usage::

        tracker = DebateTracker()
        tracker.track_debate(stock_code="600519", bull_signal="buy", ...)
        tracker.evaluate_outcome(record_id="...", actual_return=3.5)
        stats = tracker.get_agent_accuracy()
    """

    def __init__(self, persist_dir: str = _DEFAULT_TRACKER_DIR):
        self.persist_dir = persist_dir
        self._records: List[DebateRecord] = []
        self._load()

    def track_debate(
        self,
        stock_code: str,
        date: str,
        bull_signal: str,
        bull_confidence: float,
        bear_signal: str,
        bear_confidence: float,
        final_signal: str,
        final_confidence: float,
    ) -> str:
        """Record a debate for later evaluation."""
        record = DebateRecord(
            record_id=f"debate_{int(time.time() * 1000)}",
            stock_code=stock_code,
            date=date,
            bull_signal=bull_signal,
            bull_confidence=bull_confidence,
            bear_signal=bear_signal,
            bear_confidence=bear_confidence,
            final_signal=final_signal,
            final_confidence=final_confidence,
        )
        self._records.append(record)
        self._save()
        return record.record_id

    def evaluate_outcome(
        self,
        record_id: str,
        actual_return: float,
    ) -> Optional[Dict[str, bool]]:
        """Evaluate a tracked debate against the actual outcome."""
        actual_signal = "buy" if actual_return > 1 else ("sell" if actual_return < -1 else "hold")

        for record in self._records:
            if record.record_id == record_id and record.bull_correct is None:
                record.actual_return = actual_return
                record.bull_correct = (record.bull_signal == actual_signal)
                record.bear_correct = (record.bear_signal == actual_signal)
                self._save()
                return {"bull_correct": record.bull_correct, "bear_correct": record.bear_correct}
        return None

    def get_agent_accuracy(self) -> Dict[str, Any]:
        """Compute accuracy for Bull and Bear agents."""
        bull_total = sum(1 for r in self._records if r.bull_correct is not None)
        bull_correct = sum(1 for r in self._records if r.bull_correct is True)
        bear_total = sum(1 for r in self._records if r.bear_correct is not None)
        bear_correct = sum(1 for r in self._records if r.bear_correct is True)

        return {
            "bull_accuracy": bull_correct / bull_total if bull_total > 0 else None,
            "bull_correct": bull_correct,
            "bull_total": bull_total,
            "bear_accuracy": bear_correct / bear_total if bear_total > 0 else None,
            "bear_correct": bear_correct,
            "bear_total": bear_total,
            "total_tracked": len(self._records),
            "evaluated": sum(1 for r in self._records if r.bull_correct is not None),
        }

    def get_insights(self) -> List[str]:
        """Generate plain-language insights from debate tracking."""
        stats = self.get_agent_accuracy()
        insights = []

        bull_acc = stats.get("bull_accuracy")
        bear_acc = stats.get("bear_accuracy")

        if bull_acc is not None and bear_acc is not None:
            if bull_acc > bear_acc + 0.1:
                insights.append(
                    f"Bull agent is more accurate ({bull_acc:.0%} vs {bear_acc:.0%}) "
                    f"— consider weighting Bull arguments more heavily"
                )
            elif bear_acc > bull_acc + 0.1:
                insights.append(
                    f"Bear agent is more accurate ({bear_acc:.0%} vs {bull_acc:.0%}) "
                    f"— consider weighting Bear arguments more heavily"
                )

        if stats["evaluated"] > 0:
            insights.append(
                f"Tracked {stats['evaluated']} debates: "
                f"Bull {stats['bull_correct']}/{stats['bull_total']} correct, "
                f"Bear {stats['bear_correct']}/{stats['bear_total']} correct"
            )

        return insights

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_tracked": len(self._records),
            "evaluated": sum(1 for r in self._records if r.bull_correct is not None),
            "unaudited": sum(1 for r in self._records if r.bull_correct is None),
            **self.get_agent_accuracy(),
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
                self._records = []
                for item in data:
                    try:
                        record = DebateRecord.from_dict(item)
                        self._records.append(record)
                    except (TypeError, KeyError):
                        continue

            logger.info(
                "[DebateTracker] loaded %d records from %s",
                len(self._records), path,
            )
        except Exception as exc:
            logger.warning("[DebateTracker] failed to load records: %s", exc)

    def _save(self) -> None:
        path = self._path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    [r.to_dict() for r in self._records],
                    f, ensure_ascii=False, indent=2,
                )
            logger.debug(
                "[DebateTracker] saved %d records to %s",
                len(self._records), path,
            )
        except Exception as exc:
            logger.warning("[DebateTracker] failed to save records: %s", exc)

    def _path(self) -> Path:
        return Path(self.persist_dir) / "debate_tracker.json"
