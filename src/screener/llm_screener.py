# -*- coding: utf-8 -*-
"""
===================================
选股选债系统 - LLM 筛选器
===================================

职责：
1. 使用 LLM 根据策略指令筛选候选股票
2. 复用现有的 GeminiAnalyzer 进行 LLM 调用
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Optional

try:
    from json_repair import repair_json
except ImportError:
    repair_json = None  # type: ignore

from src.config import Config, get_config
from src.screener.schemas import ScreenerStrategy, ScreenerCandidate
from src.screener.base import BaseScreener

logger = logging.getLogger(__name__)


class LLMScreener(BaseScreener):
    """使用 LLM 进行股票筛选"""

    def __init__(self, strategy: ScreenerStrategy, config: Optional[Config] = None):
        super().__init__(strategy)
        self.config = config or get_config()
        self._analyzer = None

    def _get_analyzer(self):
        """Lazy init GeminiAnalyzer to avoid import-time side effects"""
        if self._analyzer is None:
            from src.analyzer import GeminiAnalyzer
            self._analyzer = GeminiAnalyzer(config=self.config)
        return self._analyzer

    async def screen(
        self,
        market: str = "cn",
        max_candidates: int = 10,
        progress_callback=None,
    ) -> List[ScreenerCandidate]:
        """
        执行 LLM 筛选

        Args:
            market: 市场 (cn/us/hk)
            max_candidates: 最大候选数量
            progress_callback: 进度回调

        Returns:
            候选股票列表
        """
        prompt = self._build_prompt(market, max_candidates)
        logger.info("LLM 筛选 prompt 长度: %d 字符 (策略: %s)", len(prompt), self._strategy.name)

        if progress_callback:
            progress_callback(10, "正在调用 LLM 进行筛选...")

        loop = asyncio.get_event_loop()

        def sync_call():
            analyzer = self._get_analyzer()
            return analyzer.generate_text(
                prompt=prompt,
                max_tokens=4096,
                temperature=0.7,
            )

        response = await loop.run_in_executor(None, sync_call)

        if progress_callback:
            progress_callback(80, "正在解析 LLM 返回结果...")

        candidates = self._parse_llm_response(response)
        logger.info("LLM 返回 %d 个候选", len(candidates))

        if progress_callback:
            progress_callback(100, f"筛选完成，共 {len(candidates)} 个候选")

        return candidates

    def _build_prompt(self, market: str, max_candidates: int) -> str:
        """构建 LLM 筛选 prompt"""
        market_name = {"cn": "A股", "hk": "港股", "us": "美股"}.get(market, "A股")

        return f"""你是一位专业的{market_name}选股专家。请根据以下策略要求，从{market_name}市场中筛选出符合条件的股票。

## 策略信息
策略名称：{self._strategy.display_name}
策略描述：{self._strategy.description}
策略类别：{self._strategy.category.value}

## 策略指令
{self._strategy.instructions}

## 筛选要求
1. 市场：{market_name}
2. 最多返回 {max_candidates} 只股票
3. 请确保推荐的股票是{market_name}市场中真实存在的
4. 每只股票的入选理由应简洁明了

## 输出格式
请严格按以下 JSON 数组格式返回结果，不要输出其他内容：
```json
[
    {{"code": "6位数字股票代码", "name": "股票中文名称", "reason": "入选理由（50字以内）", "score": 评分(0-100的整数)}}
]
```

如果找不到符合条件的股票，返回空数组 []。"""

    def _parse_llm_response(self, response: Optional[str]) -> List[ScreenerCandidate]:
        """解析 LLM 返回的 JSON 响应"""
        if not response:
            logger.warning("LLM 返回为空")
            return []

        try:
            # Try to extract JSON from markdown code blocks
            text = response.strip()
            if "```json" in text:
                start = text.index("```json") + 7
                end = text.index("```", start)
                text = text[start:end].strip()
            elif "```" in text:
                start = text.index("```") + 3
                end = text.index("```", start)
                text = text[start:end].strip()

            # Try standard JSON parse first, fall back to repair
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                repaired = repair_json(text)
                data = json.loads(repaired)

            if not isinstance(data, list):
                logger.warning("LLM 返回的不是 JSON 数组")
                return []

            candidates = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                code = item.get("code", "")
                name = item.get("name", "")
                if not code or not name:
                    continue
                candidates.append(ScreenerCandidate(
                    code=str(code),
                    name=str(name),
                    reason=str(item.get("reason", "")),
                    score=float(item["score"]) if "score" in item else None,
                    metadata={k: v for k, v in item.items() if k not in ("code", "name", "reason", "score")},
                ))
            return candidates

        except Exception as e:
            logger.error("解析 LLM 响应失败: %s", e, exc_info=True)
            return []
