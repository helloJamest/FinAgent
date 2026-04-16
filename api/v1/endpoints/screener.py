# -*- coding: utf-8 -*-
"""
===================================
选股筛选 API 接口
===================================

职责：
1. POST /api/v1/screener/screen - 创建筛选任务
2. GET  /api/v1/screener/results/{task_id} - 获取筛选结果
3. GET  /api/v1/screener/strategies - 获取策略列表
4. GET  /api/v1/screener/strategies/{name} - 获取策略详情
"""

import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from api.deps import get_config_dep
from src.config import Config
from src.screener.service import ScreenerService, get_screener_service
from src.screener.pipeline import ScreenerPipeline
from api.v1.schemas.screener import (
    ScreenerScreenRequest,
    TaskAccepted,
    ScreenerResultResponse,
    ScreenerStrategyResponse,
)
from src.screener.board_screener import BoardDataFetcher

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_service() -> ScreenerService:
    return get_screener_service()


def _get_pipeline(config: Config) -> ScreenerPipeline:
    return ScreenerPipeline(config=config)


# ============================================================
# POST /screen - 创建筛选任务
# ============================================================

@router.post(
    "/screen",
    response_model=TaskAccepted,
    summary="创建筛选任务",
    description="启动选股筛选任务，异步执行，返回 task_id 用于查询结果",
)
async def create_screen_task(
    request: ScreenerScreenRequest,
    config: Config = Depends(get_config_dep),
):
    """创建筛选任务"""
    service = _get_service()

    # Validate strategy exists
    pipeline = _get_pipeline(config)
    available = [s.name for s in pipeline.available_strategies]
    if request.strategy not in available:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_strategy",
                "message": f"策略 '{request.strategy}' 不存在。可用策略: {', '.join(available)}",
            },
        )

    task = service.create_task(
        strategy=request.strategy,
        market=request.market,
        max_candidates=request.max_candidates,
        validate=request.data_validation,
        analyze_after_screen=request.analyze_after_screen,
    )

    return TaskAccepted(
        task_id=task.task_id,
        status="accepted",
        message="筛选任务已接受",
    )


# ============================================================
# GET /results/{task_id} - 获取筛选结果
# ============================================================

@router.get(
    "/results/{task_id}",
    response_model=ScreenerResultResponse,
    summary="获取筛选结果",
    description="根据 task_id 获取筛选结果",
)
async def get_screen_result(task_id: str):
    """获取筛选结果"""
    service = _get_service()
    task = service.get_task(task_id)

    if not task:
        raise HTTPException(
            status_code=404,
            detail={"error": "task_not_found", "message": "未找到该筛选任务"},
        )

    if task.status.value in ("pending", "processing"):
        raise HTTPException(
            status_code=202,
            detail={
                "error": "task_running",
                "message": "任务正在执行中，请稍后重试",
            },
        )

    if task.status.value == "failed":
        raise HTTPException(
            status_code=500,
            detail={"error": "task_failed", "message": task.error or "筛选任务失败"},
        )

    if not task.result:
        raise HTTPException(
            status_code=500,
            detail={"error": "task_error", "message": "任务已完成但无结果"},
        )

    result = task.result
    return ScreenerResultResponse(
        task_id=result.task_id,
        strategy=result.strategy,
        status=result.status,
        candidates=result.candidates,
        failed=result.failed,
        total_analyzed=result.total_analyzed,
        validation_results=result.validation_results,
    )


# ============================================================
# GET /strategies - 获取策略列表
# ============================================================

@router.get(
    "/strategies",
    response_model=List[ScreenerStrategyResponse],
    summary="获取策略列表",
    description="返回所有可用的选股策略",
)
async def list_strategies(config: Config = Depends(get_config_dep)):
    """获取所有可用的选股策略"""
    pipeline = _get_pipeline(config)
    strategies = pipeline.available_strategies
    return [
        ScreenerStrategyResponse(
            name=s.name,
            display_name=s.display_name,
            description=s.description,
            category=s.category,
            default_priority=s.default_priority,
        )
        for s in strategies
    ]


# ============================================================
# GET /strategies/{name} - 获取策略详情
# ============================================================

@router.get(
    "/strategies/{name}",
    response_model=ScreenerStrategyResponse,
    summary="获取策略详情",
    description="获取指定策略的详细信息",
)
async def get_strategy(
    name: str,
    config: Config = Depends(get_config_dep),
):
    """获取指定策略详情"""
    pipeline = _get_pipeline(config)
    strategy = pipeline._strategy_parser.get_strategy(name)
    if not strategy:
        raise HTTPException(
            status_code=404,
            detail={"error": "strategy_not_found", "message": f"策略 '{name}' 不存在"},
        )
    return ScreenerStrategyResponse(
        name=strategy.name,
        display_name=strategy.display_name,
        description=strategy.description,
        category=strategy.category,
        default_priority=strategy.default_priority,
    )


# ============================================================
# GET /board - 获取打板策略数据
# ============================================================

class BoardDataResponse(BaseModel):
    """打板策略数据响应"""
    trade_date: str = Field(..., description="交易日期")
    lhb_count: int = Field(0, description="龙虎榜条目数")
    limit_up_count: int = Field(0, description="涨停股数")
    previous_limit_up_count: int = Field(0, description="昨日涨停数")
    concept_count: int = Field(0, description="涨停概念数")
    chain_ladder: Dict[str, Any] = Field(default_factory=dict, description="连板天梯")
    concepts: List[Dict[str, Any]] = Field(default_factory=list, description="热门概念板块")
    limit_up_stocks: List[Dict[str, Any]] = Field(default_factory=list, description="涨停池")
    lhb_stocks: List[Dict[str, Any]] = Field(default_factory=list, description="龙虎榜")


@router.get(
    "/board",
    response_model=BoardDataResponse,
    summary="获取打板策略数据",
    description="获取龙虎榜、涨停池、连板天梯、涨停概念等打板相关数据",
)
async def get_board_data(
    trade_date: Optional[str] = Query(None, description="交易日期 YYYYMMDD，默认今日"),
):
    """获取打板策略数据"""
    fetcher = BoardDataFetcher()
    data = fetcher.get_all_board_data(trade_date=trade_date)

    chain_ladder = {}
    for level, stocks in data.get("chain_ladder", {}).items():
        chain_ladder[level] = [s.to_dict() if hasattr(s, "to_dict") else s for s in stocks]

    concepts = [
        c.to_dict() if hasattr(c, "to_dict") else c
        for c in data.get("concepts", [])
    ]

    limit_up = [
        s.to_dict() if hasattr(s, "to_dict") else s
        for s in data.get("limit_up", [])
    ]

    lhb = [
        e.to_dict() if hasattr(e, "to_dict") else e
        for e in data.get("lhb", [])
    ]

    return BoardDataResponse(
        trade_date=data.get("trade_date", ""),
        lhb_count=len(data.get("lhb", [])),
        limit_up_count=len(data.get("limit_up", [])),
        previous_limit_up_count=len(data.get("previous_limit_up", [])),
        concept_count=len(data.get("concepts", [])),
        chain_ladder=chain_ladder,
        concepts=concepts,
        limit_up_stocks=limit_up,
        lhb_stocks=lhb,
    )
