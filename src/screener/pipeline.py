# -*- coding: utf-8 -*-
"""
===================================
选股选债系统 - 筛选流水线
===================================

职责：
1. 编排完整的筛选流程
2. 加载策略 -> LLM筛选 -> (可选)数据验证 -> 输出结果
"""

import asyncio
import logging
import uuid
from typing import Optional, Dict, Any, Callable

from src.config import Config, get_config
from src.screener.schemas import (
    ScreenerOptions,
    ScreenerResult,
    ScreenerCandidate,
    ScreenerFailedItem,
)
from src.screener.strategy import StrategyParser
from src.screener.llm_screener import LLMScreener
from src.screener.validator import DataValidator

logger = logging.getLogger(__name__)


class ScreenerPipeline:
    """选股选债流水线"""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
        self._strategy_parser = StrategyParser()
        self._results: Dict[str, ScreenerResult] = {}

    async def run(
        self,
        strategy_name: str,
        market: str = "cn",
        max_candidates: int = 10,
        validate: bool = False,
        analyze_after_screen: bool = False,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> ScreenerResult:
        """
        执行完整筛选流程

        流程：
        1. 加载策略配置
        2. LLM筛选候选股票
        3. (可选) 数据验证
        4. (可选) 调用分析系统
        5. 返回结果

        Args:
            strategy_name: 策略名称
            market: 市场 (cn/us/hk)
            max_candidates: 最大候选数量
            validate: 是否进行数据验证
            analyze_after_screen: 筛选后是否进行分析
            progress_callback: 进度回调 (percent, message)

        Returns:
            ScreenerResult: 筛选结果
        """
        task_id = str(uuid.uuid4())[:8]

        # 1. 加载策略配置
        if progress_callback:
            progress_callback(0, f"正在加载策略: {strategy_name}")

        strategy = self._strategy_parser.get_strategy(strategy_name)
        if not strategy:
            available = [s.name for s in self._strategy_parser.list_strategies()]
            raise ValueError(
                f"策略 '{strategy_name}' 不存在。可用策略: {', '.join(available)}"
            )

        logger.info("开始选股筛选 (任务: %s, 策略: %s)", task_id, strategy_name)

        # 2. LLM筛选
        if progress_callback:
            progress_callback(5, "正在初始化 LLM 筛选器...")

        screener = LLMScreener(strategy=strategy, config=self.config)
        candidates = await screener.screen(
            market=market,
            max_candidates=max_candidates,
            progress_callback=progress_callback,
        )

        total_analyzed = len(candidates)
        failed: list[ScreenerFailedItem] = []

        if not candidates:
            if progress_callback:
                progress_callback(100, "未找到符合条件的股票")
            return ScreenerResult(
                task_id=task_id,
                strategy=strategy_name,
                status="completed",
                candidates=[],
                failed=[],
                total_analyzed=0,
            )

        # 3. 数据验证（可选）
        validation_results = None
        if validate and candidates:
            if progress_callback:
                progress_callback(85, "正在进行数据验证...")

            validator = DataValidator()
            passed, validation_failed = validator.validate_batch(
                candidates=candidates,
                progress_callback=progress_callback,
            )
            candidates = passed
            failed = validation_failed
            total_analyzed = len(passed) + len(validation_failed)
            validation_results = {
                "passed": len(passed),
                "failed": len(validation_failed),
            }

        # 4. 调用分析系统（可选，暂不实现）
        if analyze_after_screen:
            logger.info("analyze_after_screen 暂未实现，跳过")

        result = ScreenerResult(
            task_id=task_id,
            strategy=strategy_name,
            status="completed",
            candidates=candidates,
            failed=failed,
            total_analyzed=total_analyzed,
            validation_results=validation_results,
        )

        self._results[task_id] = result
        logger.info(
            "筛选完成 (任务: %s, 通过: %d, 失败: %d)",
            task_id, len(candidates), len(failed),
        )
        return result

    def get_result(self, task_id: str) -> Optional[ScreenerResult]:
        """获取筛选结果"""
        return self._results.get(task_id)

    def list_results(self) -> Dict[str, ScreenerResult]:
        """列出所有结果"""
        return dict(self._results)

    @property
    def available_strategies(self):
        """获取可用策略列表"""
        return self._strategy_parser.list_strategies()
