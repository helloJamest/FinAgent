# -*- coding: utf-8 -*-
"""
===================================
选股选债系统 - 策略解析器
===================================

职责：
1. 从 YAML 文件加载选股策略
2. 解析策略配置为 ScreenerStrategy 模型
3. 只处理 screen_*.yaml 和 bond_*.yaml（分析策略被排除）
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict

import yaml

from src.screener.schemas import ScreenerStrategy, ScreenerCategory, AssetType

logger = logging.getLogger(__name__)


_STRATEGIES_DIR = Path(__file__).parent / "strategies"


class StrategyParser:
    """策略解析器，只处理选股/选债策略"""

    def __init__(self, strategies_dir: Optional[Path] = None):
        self._strategies_dir = strategies_dir or _STRATEGIES_DIR
        self._strategies: Dict[str, ScreenerStrategy] = {}
        self._load_strategies()

    def _load_strategies(self) -> None:
        """从策略目录加载所有选股/选债策略"""
        if not self._strategies_dir.exists():
            logger.warning("策略目录不存在: %s", self._strategies_dir)
            return

        for yaml_file in sorted(self._strategies_dir.glob("*.yaml")):
            strategy = self._load_strategy_file(yaml_file)
            if strategy:
                self._strategies[strategy.name] = strategy

        logger.info("已加载 %d 个选股/选债策略", len(self._strategies))

    def _load_strategy_file(self, yaml_path: Path) -> Optional[ScreenerStrategy]:
        """加载单个策略 YAML 文件"""
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data or not isinstance(data, dict):
                return None
            return self._parse_strategy_data(data)
        except Exception as e:
            logger.warning("加载策略文件失败 %s: %s", yaml_path, e)
            return None

    def _parse_strategy_data(self, data: dict) -> Optional[ScreenerStrategy]:
        """
        解析策略数据

        关键：只处理 screen_*.yaml 和 bond_*.yaml
        分析策略（如 bull_trend）被自动排除
        """
        name = data.get("name", "")
        if not name:
            return None

        # 只处理选股和选债策略
        if not (name.startswith("screen_") or name.startswith("bond_")):
            return None

        # 暂时只加载选股策略
        if not name.startswith("screen_"):
            return None

        try:
            category = ScreenerCategory(data.get("category", "value"))
        except ValueError:
            category = ScreenerCategory.VALUE

        return ScreenerStrategy(
            name=name,
            display_name=data.get("display_name", name),
            description=data.get("description", ""),
            category=category,
            default_active=data.get("default_active", True),
            default_priority=data.get("default_priority", 10),
            required_tools=data.get("required_tools", []),
            aliases=data.get("aliases", []),
            instructions=data.get("instructions", ""),
        )

    def get_strategy(self, name: str) -> Optional[ScreenerStrategy]:
        """获取指定策略"""
        return self._strategies.get(name)

    def list_strategies(self, asset_type: Optional[AssetType] = None) -> List[ScreenerStrategy]:
        """
        列出所有可用策略

        Args:
            asset_type: 资产类型过滤（stock/bond）
        """
        strategies = list(self._strategies.values())
        if asset_type == AssetType.STOCK:
            strategies = [s for s in strategies if s.name.startswith("screen_")]
        elif asset_type == AssetType.BOND:
            strategies = [s for s in strategies if s.name.startswith("bond_")]
        return sorted(strategies, key=lambda s: s.default_priority, reverse=True)

    @property
    def strategy_count(self) -> int:
        """已加载策略数量"""
        return len(self._strategies)
