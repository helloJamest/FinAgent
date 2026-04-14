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
from typing import List

from fastapi import APIRouter, HTTPException, Depends

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
        validate=request.validate,
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
