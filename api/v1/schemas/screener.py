# -*- coding: utf-8 -*-
"""
===================================
选股筛选相关模型
===================================

职责：
1. 定义筛选 API 请求和响应模型
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from src.screener.schemas import ScreenerCandidate, ScreenerFailedItem, ScreenerCategory


class ScreenerScreenRequest(BaseModel):
    """筛选请求"""
    strategy: str = Field(..., description="策略名称，如 screen_three_line")
    market: str = Field(default="cn", description="市场: cn/us/hk")
    max_candidates: int = Field(default=10, description="最大候选数量", ge=1, le=100)
    data_validation: bool = Field(default=False, description="是否进行数据验证")
    analyze_after_screen: bool = Field(default=False, description="筛选后是否进行分析")


class TaskAccepted(BaseModel):
    """任务已接受响应"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(default="accepted", description="状态")
    message: str = Field(default="筛选任务已接受", description="消息")


class ScreenerResultResponse(BaseModel):
    """筛选结果响应"""
    task_id: str = Field(..., description="任务ID")
    strategy: str = Field(..., description="策略名称")
    status: str = Field(default="completed", description="状态")
    candidates: List[ScreenerCandidate] = Field(default_factory=list, description="通过的候选列表")
    failed: List[ScreenerFailedItem] = Field(default_factory=list, description="失败列表")
    total_analyzed: int = Field(default=0, description="总共分析数量")
    validation_results: Optional[Dict[str, Any]] = Field(default=None, description="验证结果")


class ScreenerStrategyResponse(BaseModel):
    """策略信息响应"""
    name: str = Field(..., description="策略名称")
    display_name: str = Field(..., description="显示名称")
    description: str = Field(..., description="策略描述")
    category: ScreenerCategory = Field(..., description="策略类别")
    default_priority: int = Field(default=10, description="优先级")
