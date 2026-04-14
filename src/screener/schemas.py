# -*- coding: utf-8 -*-
"""
===================================
选股选债系统 - 数据模型
===================================

职责：
1. 定义策略配置模型
2. 定义筛选候选结果模型
3. 定义筛选结果模型
"""

from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


class ScreenerCategory(str, Enum):
    """策略类别"""
    VALUE = "value"              # 价值类
    MOMENTUM = "momentum"        # 动量类
    REVERSAL = "reversal"        # 反转类
    FRAMEWORK = "framework"      # 框架类


class AssetType(str, Enum):
    """资产类型"""
    STOCK = "stock"
    BOND = "bond"


class ScreenerStrategy(BaseModel):
    """策略配置模型"""
    name: str = Field(..., description="策略名称，如 screen_dual_low")
    display_name: str = Field(..., description="显示名称，如 双低选股策略")
    description: str = Field(..., description="策略描述")
    category: ScreenerCategory = Field(default=ScreenerCategory.VALUE)
    default_active: bool = Field(default=True, description="是否默认激活")
    default_priority: int = Field(default=10, description="策略优先级")
    required_tools: List[str] = Field(default_factory=list, description="所需工具列表")
    aliases: List[str] = Field(default_factory=list, description="策略别名")
    instructions: str = Field(default="", description="策略指令（用于LLM prompt）")


class ScreenerCandidate(BaseModel):
    """筛选候选结果"""
    code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    reason: str = Field(default="", description="入选理由")
    score: Optional[float] = Field(default=None, description="评分（如有）")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加信息")


class ScreenerFailedItem(BaseModel):
    """筛选失败项"""
    code: str = Field(..., description="股票代码")
    name: str = Field(default="", description="股票名称")
    error: str = Field(default="", description="失败原因")


class ScreenerResult(BaseModel):
    """筛选结果"""
    task_id: str = Field(..., description="任务ID")
    strategy: str = Field(..., description="策略名称")
    status: str = Field(default="completed", description="状态")
    candidates: List[ScreenerCandidate] = Field(default_factory=list, description="通过的候选列表")
    failed: List[ScreenerFailedItem] = Field(default_factory=list, description="失败列表")
    total_analyzed: int = Field(default=0, description="总共分析数量")
    validation_results: Optional[Dict[str, Any]] = Field(default=None, description="验证结果")


class ScreenerOptions(BaseModel):
    """筛选选项"""
    strategy: str = Field(..., description="策略名称")
    market: str = Field(default="cn", description="市场: cn/us/hk")
    max_candidates: int = Field(default=10, description="最大候选数量", ge=1, le=100)
    do_validate: bool = Field(default=False, description="是否进行数据验证")
    analyze_after_screen: bool = Field(default=False, description="筛选后是否进行分析")


class ScreenerStrategyInfo(BaseModel):
    """策略信息（用于API返回策略列表）"""
    name: str = Field(..., description="策略名称")
    display_name: str = Field(..., description="显示名称")
    description: str = Field(..., description="策略描述")
    category: ScreenerCategory = Field(..., description="策略类别")
    default_priority: int = Field(default=10, description="优先级")
