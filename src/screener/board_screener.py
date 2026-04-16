# -*- coding: utf-8 -*-
"""
===================================
打板策略 - Board Screener
===================================

职责：
1. 获取龙虎榜、涨停池、连板天梯、涨停概念数据
2. 自动筛选 1进2/2进3/3进4 晋级股
3. 结合板块热度生成候选股票
4. 可选 LLM 深度分析生成策略建议

数据源：AKShare 东方财富接口
- stock_lhb_hyyyb_em: 龙虎榜游资营业部数据
- stock_zt_pool_em: 涨停池
- stock_zt_pool_previous_em: 昨日涨停池
- stock_zt_concept_em: 涨停概念板块
- stock_zt_pool_strong_em: 强势连板股（连板天梯）
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable

from src.screener.schemas import ScreenerCandidate, ScreenerStrategy
from src.screener.base import BaseScreener

logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


class BoardDataFetcher:
    """
    打板数据获取器

    通过 AKShare 获取 A 股打板相关的核心数据。
    """

    def __init__(self):
        self._ak = None

    def _get_ak(self):
        if self._ak is None:
            import akshare as ak
            self._ak = ak
        return self._ak

    def _safe_sleep(self, seconds: float = 2.0):
        import random, time
        delay = random.uniform(seconds * 0.8, seconds * 1.2)
        time.sleep(delay)

    def _row_val(self, row: Any, key: str, default: Any = None) -> Any:
        """Safely get a value from a row, handling both dict-like and Series."""
        if row is None:
            return default
        if key in row:
            val = row[key]
            return default if val is None else val
        return default

    def get_lhb_data(
        self, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """
        获取龙虎榜数据（游资营业部维度）

        Args:
            start_date: YYYYMMDD
            end_date: YYYYMMDD

        Returns:
            龙虎榜条目列表，每个包含代码/名称/上榜理由/买卖金额等
        """
        try:
            self._safe_sleep()
            ak = self._get_ak()
            df = ak.stock_lhb_hyyyb_em(start_date=start_date, end_date=end_date)
            if df is None or df.empty:
                return []

            # Log actual columns for debugging if API changes
            logger.info(f"龙虎榜数据列: {list(df.columns)}")

            results = []
            for _, row in df.iterrows():
                if row is None:
                    continue
                code = self._row_val(row, "代码", "")
                name = self._row_val(row, "名称", "")
                if not code or not name:
                    continue
                results.append({
                    "code": str(code).strip(),
                    "name": str(name).strip(),
                    "reason": str(self._row_val(row, "上榜理由", "")),
                    "buy_amount": _safe_float(self._row_val(row, "买入金额", 0)),
                    "sell_amount": _safe_float(self._row_val(row, "卖出金额", 0)),
                    "net_amount": _safe_float(self._row_val(row, "净额", 0)),
                    "close": _safe_float(self._row_val(row, "收盘价", 0)),
                    "change_pct": _safe_float(self._row_val(row, "涨跌幅", 0)),
                    "turnover_rate": _safe_float(self._row_val(row, "换手率", 0)),
                })
            return results
        except Exception as e:
            logger.warning(f"获取龙虎榜数据失败: {e}")
            return []

    def get_limit_up_pool(self, trade_date: str) -> List[Dict[str, Any]]:
        """获取当日涨停池"""
        try:
            self._safe_sleep()
            ak = self._get_ak()
            df = ak.stock_zt_pool_em(date=trade_date)
            if df is None or df.empty:
                return []
            results = []
            for _, row in df.iterrows():
                results.append({
                    "code": str(row.get("代码", "")).strip(),
                    "name": str(row.get("名称", "")).strip(),
                    "close": _safe_float(row.get("收盘价", 0)),
                    "change_pct": _safe_float(row.get("涨跌幅", 0)),
                    "consecutive_days": _safe_int(row.get("连板数", 1)),
                    "limit_up_time": str(row.get("首次封板时间", "")),
                    "turnover_rate": _safe_float(row.get("换手率", 0)),
                    "volume_ratio": _safe_float(row.get("量比", 0)),
                    "sector": str(row.get("所属题材", row.get("板块", ""))),
                })
            return results
        except Exception as e:
            logger.warning(f"获取涨停池数据失败: {e}")
            return []

    def get_previous_limit_up(self, trade_date: str) -> List[Dict[str, Any]]:
        """获取昨日涨停池（用于分析晋级情况）"""
        try:
            self._safe_sleep()
            ak = self._get_ak()
            df = ak.stock_zt_pool_previous_em(date=trade_date)
            if df is None or df.empty:
                return []
            results = []
            for _, row in df.iterrows():
                results.append({
                    "code": str(row.get("代码", "")).strip(),
                    "name": str(row.get("名称", "")).strip(),
                    "close": _safe_float(row.get("收盘价", 0)),
                    "change_pct": _safe_float(row.get("涨跌幅", 0)),
                    "consecutive_days": _safe_int(row.get("连板数", 1)),
                    "limit_up_time": str(row.get("首次封板时间", "")),
                    "turnover_rate": _safe_float(row.get("换手率", 0)),
                    "volume_ratio": _safe_float(row.get("量比", 0)),
                    "sector": str(row.get("所属题材", row.get("板块", ""))),
                })
            return results
        except Exception as e:
            logger.warning(f"获取昨日涨停池数据失败: {e}")
            return []

    def get_zt_concepts(self) -> List[Dict[str, Any]]:
        """获取涨停概念/板块，按公司家数降序"""
        try:
            self._safe_sleep()
            ak = self._get_ak()
            # stock_zt_concept_em 不存在，使用 stock_board_concept_summary_ths 替代
            df = ak.stock_board_concept_summary_ths()
            if df is None or df.empty:
                return []
            results = []
            for _, row in df.iterrows():
                leader_name = str(row.get("领涨股票", "")).strip()
                results.append({
                    "sector_name": str(row.get("板块名称", "")).strip(),
                    "limit_up_count": _safe_int(row.get("成分公司数量", 0)),
                    "leader_code": "",  # ths 接口不提供领涨代码
                    "leader_name": leader_name,
                    "change_pct": 0.0,  # ths 接口不提供板块涨跌幅
                    "turnover_rate": _safe_float(row.get("换手率", 0)),
                })
            results.sort(key=lambda x: x["limit_up_count"], reverse=True)
            return results
        except Exception as e:
            logger.warning(f"获取涨停概念数据失败: {e}")
            return []

    def get_strong_chain(self, trade_date: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取连板天梯（强势连板股），按连板数分组

        Returns:
            {"1进2": [...], "2进3": [...], "3进4": [...], "4板+": [...]}
        """
        try:
            self._safe_sleep()
            ak = self._get_ak()
            df = ak.stock_zt_pool_strong_em(date=trade_date)
            if df is None or df.empty:
                return {}
            chain_groups: Dict[str, List[Dict[str, Any]]] = {}
            for _, row in df.iterrows():
                consecutive = _safe_int(row.get("连板数", 1))
                stock = {
                    "code": str(row.get("代码", "")).strip(),
                    "name": str(row.get("名称", "")).strip(),
                    "close": _safe_float(row.get("收盘价", 0)),
                    "change_pct": _safe_float(row.get("涨跌幅", 0)),
                    "consecutive_days": consecutive,
                    "limit_up_time": str(row.get("首次封板时间", "")),
                    "turnover_rate": _safe_float(row.get("换手率", 0)),
                    "volume_ratio": _safe_float(row.get("量比", 0)),
                    "sector": str(row.get("所属题材", row.get("板块", ""))),
                }
                if not stock["code"] or not stock["name"]:
                    continue

                if consecutive == 2:
                    level = "1进2"
                elif consecutive == 3:
                    level = "2进3"
                elif consecutive == 4:
                    level = "3进4"
                else:
                    level = "4板+"

                if level not in chain_groups:
                    chain_groups[level] = []
                chain_groups[level].append(stock)
            return chain_groups
        except Exception as e:
            logger.warning(f"获取连板天梯数据失败: {e}")
            return {}

    def get_all_board_data(
        self, trade_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """一次性获取所有打板数据（串行，避免并发被封）"""
        if trade_date is None:
            trade_date = datetime.now().strftime("%Y%m%d")
        trade_date = trade_date.replace("-", "")

        result: Dict[str, Any] = {
            "trade_date": trade_date,
            "lhb": [],
            "limit_up": [],
            "previous_limit_up": [],
            "concepts": [],
            "chain_ladder": {},
        }

        logger.info("开始获取打板数据...")

        result["lhb"] = self.get_lhb_data(
            start_date=trade_date, end_date=trade_date
        )
        logger.info(f"  龙虎榜: {len(result['lhb'])} 条")

        result["limit_up"] = self.get_limit_up_pool(trade_date=trade_date)
        logger.info(f"  今日涨停: {len(result['limit_up'])} 只")

        result["previous_limit_up"] = self.get_previous_limit_up(
            trade_date=trade_date
        )
        logger.info(f"  昨日涨停: {len(result['previous_limit_up'])} 只")

        result["concepts"] = self.get_zt_concepts()
        logger.info(f"  涨停概念: {len(result['concepts'])} 个")

        result["chain_ladder"] = self.get_strong_chain(trade_date=trade_date)
        chain_total = sum(len(v) for v in result["chain_ladder"].values())
        logger.info(
            f"  连板天梯: {chain_total} 只 "
            f"({list(result['chain_ladder'].keys())})"
        )

        return result


# ============================================================
# BoardScreener
# ============================================================

class BoardScreener(BaseScreener):
    """
    打板策略筛选器

    流程：
    1. 获取龙虎榜 + 涨停池 + 连板天梯 + 涨停概念数据
    2. 从连板天梯中提取 1进2/2进3/3进4 晋级股
    3. 从涨停概念中提取板块龙头
    4. 综合评分排序，返回候选股票
    5. (可选) 调用 LLM 生成策略分析
    """

    def __init__(self, strategy: ScreenerStrategy):
        super().__init__(strategy)
        self._data_fetcher = BoardDataFetcher()

    async def screen(
        self,
        market: str = "cn",
        max_candidates: int = 20,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> List[ScreenerCandidate]:
        """执行打板筛选"""
        trade_date = datetime.now().strftime("%Y%m%d")

        if progress_callback:
            progress_callback(5, "正在获取龙虎榜、涨停池、连板天梯数据...")

        # 1. 获取所有打板数据
        board_data = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._data_fetcher.get_all_board_data(trade_date=trade_date),
        )

        if progress_callback:
            progress_callback(40, "正在分析板块热度...")

        # 2. 构建候选池
        candidates = self._build_candidates(board_data, max_candidates)

        if not candidates:
            if progress_callback:
                progress_callback(100, "未找到符合条件的打板标的")
            return []

        if progress_callback:
            progress_callback(70, "正在计算综合评分...")

        # 3. 综合评分排序
        candidates = self._score_candidates(candidates, board_data)
        candidates.sort(key=lambda c: c.score or 0, reverse=True)
        candidates = candidates[:max_candidates]

        if progress_callback:
            progress_callback(85, "正在生成策略建议...")

        # 4. LLM 策略分析（可选）
        await self._attach_llm_analysis(candidates, board_data)

        if progress_callback:
            progress_callback(100, f"打板策略完成，共 {len(candidates)} 个候选")

        logger.info(
            "打板筛选完成: 候选 %d 只, 连板层级 %s",
            len(candidates),
            list(board_data.get("chain_ladder", {}).keys()),
        )
        return candidates

    # ----------------------------------------------------------
    # Candidate building
    # ----------------------------------------------------------

    def _build_candidates(
        self, board_data: Dict[str, Any], max_candidates: int
    ) -> List[ScreenerCandidate]:
        """从打板数据构建候选股票池"""
        candidates: List[ScreenerCandidate] = []
        seen_codes: set = set()

        chain_ladder = board_data.get("chain_ladder", {})

        # 优先关注 1进2, 2进3, 3进4
        priority_levels = ["1进2", "2进3", "3进4"]
        for level in priority_levels:
            stocks = chain_ladder.get(level, [])
            for stock in stocks[:5]:
                code = stock["code"]
                if code in seen_codes:
                    continue
                seen_codes.add(code)

                reason = (
                    f"{level} 晋级股"
                    f" | 板块: {stock.get('sector', '无')}"
                    f" | 换手率: {stock.get('turnover_rate', 0):.1f}%"
                    f" | 量比: {stock.get('volume_ratio', 0):.1f}"
                )
                candidates.append(ScreenerCandidate(
                    code=code,
                    name=stock["name"],
                    reason=reason,
                    score=0.0,
                    metadata={
                        "chain_level": level,
                        "consecutive_days": stock.get("consecutive_days", 1),
                        "sector": stock.get("sector", ""),
                        "turnover_rate": stock.get("turnover_rate", 0),
                        "volume_ratio": stock.get("volume_ratio", 0),
                        "limit_up_time": stock.get("limit_up_time", ""),
                    }
                ))

        # 补充：涨停概念龙头股
        concepts = board_data.get("concepts", [])[:5]
        for concept in concepts:
            leader_code = concept.get("leader_code", "")
            if leader_code and leader_code not in seen_codes:
                seen_codes.add(leader_code)
                candidates.append(ScreenerCandidate(
                    code=leader_code,
                    name=concept.get("leader_name", ""),
                    reason=(
                        f"板块龙头 | {concept['sector_name']} "
                        f"(涨停 {concept['limit_up_count']} 只)"
                    ),
                    score=0.0,
                    metadata={
                        "chain_level": "概念龙头",
                        "sector": concept.get("sector_name", ""),
                        "sector_limit_up_count": concept.get(
                            "limit_up_count", 0
                        ),
                    }
                ))

        # 补充：龙虎榜上榜但尚未在候选池中的股票
        lhb_entries = board_data.get("lhb", [])
        for entry in lhb_entries[:5]:
            code = entry["code"]
            if code and code not in seen_codes:
                seen_codes.add(code)
                net = entry.get("net_amount", 0)
                candidates.append(ScreenerCandidate(
                    code=code,
                    name=entry["name"],
                    reason=(
                        f"龙虎榜 | {entry.get('reason', '游资上榜')}"
                        f" | 净买入 {net/1e8:.2f} 亿"
                    ),
                    score=0.0,
                    metadata={
                        "chain_level": "龙虎榜",
                        "sector": "",
                        "net_amount": net,
                    }
                ))

        return candidates[:max_candidates]

    # ----------------------------------------------------------
    # Scoring
    # ----------------------------------------------------------

    def _score_candidates(
        self,
        candidates: List[ScreenerCandidate],
        board_data: Dict[str, Any],
    ) -> List[ScreenerCandidate]:
        """对候选股票综合评分"""
        # 构建热门板块集合（涨停家数前 5）
        concepts = board_data.get("concepts", [])[:5]
        hot_sectors = {c["sector_name"] for c in concepts}

        # 龙虎榜代码集合
        lhb_codes = {
            e["code"] for e in board_data.get("lhb", []) if e.get("code")
        }

        for c in candidates:
            score = 0.0
            meta = c.metadata

            # 1) 连板晋级系数 (最高 30 分)
            chain_level = meta.get("chain_level", "")
            if chain_level == "1进2":
                score += 10
            elif chain_level == "2进3":
                score += 15
            elif chain_level == "3进4":
                score += 20
            elif chain_level == "4板+":
                score += 10  # 高位板风险增大

            # 2) 板块热度 (最高 20 分)
            sector = meta.get("sector", "")
            if sector in hot_sectors:
                # 按板块涨停家数给分
                for con in concepts:
                    if con["sector_name"] == sector:
                        score += min(con["limit_up_count"] * 2, 20)
                        break

            # 3) 龙虎榜上榜 (15 分)
            if c.code in lhb_codes:
                score += 15

            # 4) 量比 (最高 10 分)
            vr = meta.get("volume_ratio", 0)
            if vr > 2:
                score += 10
            elif vr > 1.5:
                score += 7
            elif vr > 1:
                score += 3

            # 5) 换手率适中 (最高 10 分)
            tr = meta.get("turnover_rate", 0)
            if 10 <= tr <= 20:
                score += 10
            elif 5 <= tr < 10 or 20 < tr <= 30:
                score += 5

            c.score = score

        return candidates

    # ----------------------------------------------------------
    # LLM analysis (optional)
    # ----------------------------------------------------------

    async def _attach_llm_analysis(
        self,
        candidates: List[ScreenerCandidate],
        board_data: Dict[str, Any],
    ) -> None:
        """调用 LLM 生成打板策略分析，附加到候选 metadata"""
        prompt = self._build_analysis_prompt(candidates, board_data)
        logger.info("LLM 打板分析 prompt 长度: %d 字符", len(prompt))

        try:
            from src.analyzer import GeminiAnalyzer
            from src.config import get_config

            config = get_config()
            analyzer = GeminiAnalyzer(config=config)

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: analyzer.generate_text(
                    prompt=prompt, max_tokens=4096, temperature=0.7
                ),
            )

            if response:
                for c in candidates:
                    c.metadata["llm_analysis"] = response
                logger.info("LLM 打板分析完成")
            else:
                logger.warning("LLM 打板分析返回为空")
        except Exception as e:
            logger.warning(f"LLM 打板分析失败: {e}")
            for c in candidates:
                c.metadata["llm_analysis"] = f"LLM 分析失败: {e}"

    def _build_analysis_prompt(
        self,
        candidates: List[ScreenerCandidate],
        board_data: Dict[str, Any],
    ) -> str:
        """构建打板策略分析 prompt"""
        chain_ladder = board_data.get("chain_ladder", {})
        concepts = board_data.get("concepts", [])[:10]
        limit_up = board_data.get("limit_up", [])[:20]

        # 连板天梯摘要
        chain_lines = []
        for level in ["1进2", "2进3", "3进4", "4板+"]:
            stocks = chain_ladder.get(level, [])
            if stocks:
                names = ", ".join(
                    f"{s['name']}({s['code']})" for s in stocks[:5]
                )
                chain_lines.append(f"- {level}: {names} (共{len(stocks)}只)")

        # 热门板块摘要
        concept_lines = []
        for c in concepts[:8]:
            concept_lines.append(
                f"- {c['sector_name']}: 涨停 {c['limit_up_count']} 只, "
                f"龙头 {c['leader_name']}({c['leader_code']}), "
                f"涨幅 {c['change_pct']:.1f}%"
            )

        # 候选股摘要
        cand_lines = []
        for c in candidates[:15]:
            cand_lines.append(
                f"- {c.name}({c.code}): {c.reason}, 评分 {c.score:.1f}"
            )

        sep = "\n"

        return f"""你是一位资深的 A 股短线打板策略分析师。请基于以下数据生成打板策略分析。

## 今日市场数据
交易日期：{board_data.get('trade_date', '今日')}

### 连板天梯
{sep.join(chain_lines) if chain_lines else '- 无连板数据'}

### 热门涨停概念板块
{sep.join(concept_lines) if concept_lines else '- 无概念数据'}

### 今日涨停池 (前 20)
{', '.join(f"{s['name']}({s['code']})" for s in limit_up[:10]) if limit_up else '- 无涨停池数据'}

### 候选打板股票 (按综合评分排序)
{sep.join(cand_lines) if cand_lines else '- 无候选'}

## 输出要求
请按以下格式输出分析结果：

📊 **板块策略**
- 今日最热门板块：[板块名]
- 参与价值：[分析原因]
- 风险提示：[该板块的风险点]

🚀 **连板晋级预测**
- 1进2重点关注：[股票名 + 原因]
- 2进3重点关注：[股票名 + 原因]
- 3进4重点关注：[股票名 + 原因]

💡 **个股买入策略**
对每只候选股票：
- 是否打板：[是/否]
- 买入时机：[竞价/早盘/尾盘]
- 风险等级：[低/中/高]
- 止损建议：[具体价位或百分比]
"""
