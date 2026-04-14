# -*- coding: utf-8 -*-
"""
===================================
选股选债系统 - 数据验证器
===================================

职责：
1. 对候选股票进行真实市场数据验证
2. 复用 DataFetcherManager 获取行情数据
"""

import logging
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor

from data_provider import DataFetcherManager
from src.screener.schemas import ScreenerCandidate, ScreenerFailedItem
from src.screener.base import BaseValidator

logger = logging.getLogger(__name__)


# 数据字段映射（策略指令中的字段 -> DataFetcher 返回的字段）
FIELD_MAPPING = {
    # 估值指标
    "pe_ttm": "pe",
    "pb": "pb",
    # 市值指标
    "total_market_cap": "total_market_cap",
    "free_market_cap": "free_market_cap",
    # 技术指标
    "ma5": "ma5",
    "ma10": "ma10",
    "ma20": "ma20",
    "ma60": "ma60",
    # 量价指标
    "volume": "volume",
    "turnover": "turnover",
    "amplitude": "amplitude",
    # 涨跌幅
    "change_pct": "pct_change",
    # 其他
    "price": "close",
}


class DataValidator(BaseValidator):
    """验证候选股票是否符合真实数据条件"""

    def __init__(self):
        super().__init__()
        self.fetcher_manager = DataFetcherManager()

    def validate_batch(
        self,
        candidates: List[ScreenerCandidate],
        max_workers: int = 3,
        progress_callback=None,
    ) -> tuple[List[ScreenerCandidate], List[ScreenerFailedItem]]:
        """
        批量验证候选股票

        Args:
            candidates: 候选股票列表
            max_workers: 最大并发数
            progress_callback: 进度回调

        Returns:
            (通过验证的候选列表, 失败列表)
        """
        passed = []
        failed = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for candidate in candidates:
                future = executor.submit(self._validate_single, candidate)
                futures[future] = candidate

            completed = 0
            for future in futures:
                candidate = futures[future]
                try:
                    result = future.result(timeout=30)
                    if result["passed"]:
                        candidate.metadata.update(result.get("data", {}))
                        passed.append(candidate)
                    else:
                        failed.append(ScreenerFailedItem(
                            code=candidate.code,
                            name=candidate.name,
                            error=result.get("error", "数据验证未通过"),
                        ))
                except Exception as e:
                    logger.warning("验证 %s 失败: %s", candidate.code, e)
                    failed.append(ScreenerFailedItem(
                        code=candidate.code,
                        name=candidate.name,
                        error=str(e),
                    ))

                completed += 1
                if progress_callback:
                    progress_callback(
                        int(completed / len(candidates) * 100),
                        f"正在验证 {candidate.code} {candidate.name}...",
                    )

        return passed, failed

    def _validate_single(self, candidate: ScreenerCandidate) -> Dict[str, Any]:
        """验证单只股票"""
        try:
            df, source = self.fetcher_manager.get_daily_data(candidate.code, days=60)
            if df is None or df.empty:
                return {"passed": False, "error": "无法获取股票数据"}

            # 基础验证：数据完整性
            if len(df) < 20:
                return {"passed": False, "error": "历史数据不足（少于20个交易日）"}

            # 排除 ST 股
            if "ST" in candidate.name.upper():
                return {"passed": False, "error": "排除 ST 股"}

            # 提取最新行情数据
            latest = df.iloc[-1]
            data = {
                "latest_price": float(latest.get("close", 0)),
                "latest_volume": float(latest.get("volume", 0)),
                "days_count": len(df),
                "data_source": source,
            }

            return {"passed": True, "data": data}

        except Exception as e:
            logger.warning("获取 %s 数据失败: %s", candidate.code, e)
            return {"passed": False, "error": f"数据获取失败: {str(e)}"}
