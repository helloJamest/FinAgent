# -*- coding: utf-8 -*-
"""
===================================
选股选债系统 - 后台任务服务
===================================

职责：
1. 管理筛选任务的生命周期
2. 支持后台异步执行筛选
3. 任务结果缓存和查询
"""

import asyncio
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any

from src.config import Config, get_config
from src.screener.pipeline import ScreenerPipeline
from src.screener.schemas import ScreenerResult

logger = logging.getLogger(__name__)


class ScreenerTaskStatus(str, Enum):
    """筛选任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ScreenerTaskInfo:
    """筛选任务信息"""

    def __init__(
        self,
        task_id: str,
        strategy: str,
        market: str = "cn",
        max_candidates: int = 10,
        validate: bool = False,
    ):
        self.task_id = task_id
        self.strategy = strategy
        self.market = market
        self.max_candidates = max_candidates
        self.validate = validate
        self.status = ScreenerTaskStatus.PENDING
        self.result: Optional[ScreenerResult] = None
        self.error: Optional[str] = None
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "strategy": self.strategy,
            "market": self.market,
            "max_candidates": self.max_candidates,
            "validate": self.validate,
            "status": self.status.value,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ScreenerService:
    """选股筛选后台任务服务"""

    _instance: Optional['ScreenerService'] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: Optional[Config] = None):
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.config = config or get_config()
        self._pipeline = ScreenerPipeline(config=self.config)
        self._tasks: Dict[str, ScreenerTaskInfo] = {}
        self._futures: Dict[str, Future] = {}
        self._max_workers = 2
        self._executor: Optional[ThreadPoolExecutor] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._data_lock = threading.RLock()
        self._initialized = True

        logger.info("[ScreenerService] 初始化完成")

    @property
    def executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self._max_workers)
        return self._executor

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """设置主事件循环（用于跨线程通知）"""
        self._loop = loop

    def create_task(
        self,
        strategy: str,
        market: str = "cn",
        max_candidates: int = 10,
        validate: bool = False,
        analyze_after_screen: bool = False,
    ) -> ScreenerTaskInfo:
        """创建筛选任务"""
        task_id = f"scr-{uuid.uuid4().hex[:8]}"
        task = ScreenerTaskInfo(
            task_id=task_id,
            strategy=strategy,
            market=market,
            max_candidates=max_candidates,
            validate=validate,
        )

        with self._data_lock:
            self._tasks[task_id] = task
            future = self.executor.submit(
                self._run_screening,
                task_id,
                strategy,
                market,
                max_candidates,
                validate,
                analyze_after_screen,
            )
            self._futures[task_id] = future
            future.add_done_callback(lambda f: self._on_task_done(task_id))

        return task

    def _run_screening(
        self,
        task_id: str,
        strategy: str,
        market: str,
        max_candidates: int,
        validate: bool,
        analyze_after_screen: bool,
    ):
        """在线程池中执行筛选"""
        task = self._tasks.get(task_id)
        if not task:
            return

        task.status = ScreenerTaskStatus.PROCESSING
        task.started_at = datetime.now()

        try:
            # ScreenerPipeline.run() is async, run it in a new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self._pipeline.run(
                        strategy_name=strategy,
                        market=market,
                        max_candidates=max_candidates,
                        validate=validate,
                        analyze_after_screen=analyze_after_screen,
                    )
                )
                task.result = result
                task.status = ScreenerTaskStatus.COMPLETED
            finally:
                loop.close()

        except Exception as e:
            logger.error("[ScreenerService] 任务 %s 失败: %s", task_id, e, exc_info=True)
            task.error = str(e)
            task.status = ScreenerTaskStatus.FAILED

        task.completed_at = datetime.now()

    def _on_task_done(self, task_id: str):
        """任务完成回调"""
        task = self._tasks.get(task_id)
        if task:
            logger.info(
                "[ScreenerService] 任务 %s 完成: %s",
                task_id, task.status.value,
            )

    def get_task(self, task_id: str) -> Optional[ScreenerTaskInfo]:
        """获取任务信息"""
        return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 20) -> List[ScreenerTaskInfo]:
        """列出最近的任务"""
        with self._data_lock:
            tasks = sorted(
                self._tasks.values(),
                key=lambda t: t.created_at,
                reverse=True,
            )
            return tasks[:limit]

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """清理过期任务"""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        with self._data_lock:
            to_remove = [
                tid for tid, task in self._tasks.items()
                if task.completed_at and task.completed_at < cutoff
            ]
            for tid in to_remove:
                del self._tasks[tid]
                self._futures.pop(tid, None)

        if to_remove:
            logger.info("[ScreenerService] 清理 %d 个过期任务", len(to_remove))


def get_screener_service() -> ScreenerService:
    """获取筛选服务单例"""
    if ScreenerService._instance is None:
        ScreenerService()
    return ScreenerService._instance
