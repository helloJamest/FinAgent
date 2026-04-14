# -*- coding: utf-8 -*-
"""
===================================
选股选债系统 - 基类定义
===================================

职责：
1. 定义筛选器基类
2. 定义验证器基类
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from src.screener.schemas import ScreenerStrategy, ScreenerCandidate, ScreenerFailedItem


class BaseScreener(ABC):
    """筛选器基类"""

    def __init__(self, strategy: ScreenerStrategy):
        self._strategy = strategy

    @abstractmethod
    async def screen(
        self,
        market: str = "cn",
        max_candidates: int = 10,
        progress_callback=None,
    ) -> List[ScreenerCandidate]:
        """执行筛选"""
        pass


class BaseValidator(ABC):
    """验证器基类"""

    def __init__(self):
        pass

    @abstractmethod
    def validate_batch(
        self,
        candidates: List[ScreenerCandidate],
        max_workers: int = 3,
        progress_callback=None,
    ) -> tuple[List[ScreenerCandidate], List[ScreenerFailedItem]]:
        """批量验证"""
        pass
