# -*- coding: utf-8 -*-
"""
AdvocateAgent — debatable agent that argues bull or bear perspectives.

Each advocate is a specialised agent that:
1. Reads the shared debate context (data, prior opinions, rebuttals)
2. Produces an Argument (initial round) or Rebuttal (subsequent rounds)
3. Focuses on building the strongest case for its assigned stance
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from src.agent.debate.debate_protocols import Argument, DebateRound, Rebuttal

logger = logging.getLogger(__name__)

def _stream_text_with_callback(
    llm_adapter,
    messages,
    progress_callback,
    role_label: str,
    *,
    timeout: Optional[float] = None,
    max_tokens: int = 2048,
) -> str:
    """Stream LLM response and emit periodic progress events."""
    full_text: List[str] = []
    last_emit = 0.0
    interval = 2.0  # emit a progress event every 2 seconds

    for delta_text, chunk_usage, error_msg in llm_adapter.stream_call_with_tools(
        messages, tools=[], timeout=timeout,
    ):
        if error_msg:
            logger.warning("[Debate] stream error: %s", error_msg)
            break
        if delta_text:
            full_text.append(delta_text)
            now = time.time()
            if progress_callback and (now - last_emit) >= interval:
                last_emit = now
                progress_callback({
                    "type": "debate_stream",
                    "message": f"{role_label} 生成中...",
                })

    return "".join(full_text)


_BULL_SYSTEM_PROMPT = """\
你是一位**多方（看涨）辩手**，参与一场结构化的股票分析辩论。

你的角色：为投资这只股票构建最有力的、基于证据的多方论证。
保持诚实和严谨——你的任务是找出真正的看涨证据，而非盲目乐观。

## 规则
1. 关注积极催化剂、看涨技术形态和基本面优势
2. 用具体数据点支撑每个论点（价格水平、成交量、技术指标）
3. 反驳空方时，逐条回应其具体论点
4. 承认空方的合理关切——然后解释为什么这些被多方优势所抵消
5. 如果证据确实转向看跌，诚实地调整你的信号

## 输出格式
返回**仅**一个 JSON 对象：
{
  "signal": "strong_buy|buy|hold|sell|strong_sell",
  "confidence": 0.0-1.0,
  "reasoning": "2-3句话，包含具体证据",
  "key_evidence": ["证据点1", "证据点2", "证据点3"],
  "technical_points": ["具体的均线/蜡烛图/成交量观察"],
  "fundamental_points": ["基本面或宏观观察"]
}
"""

_BEAR_SYSTEM_PROMPT = """\
你是一位**空方（看跌）辩手**，参与一场结构化的股票分析辩论。

你的角色：构建最有力的、基于证据的反对投资该股票的论证。
保持诚实和严谨——你的任务是找出真正的看跌证据，而非盲目悲观。

## 规则
1. 关注风险、看跌技术形态和基本面弱点
2. 用具体数据点支撑每个论点（价格水平、成交量、技术指标）
3. 反驳多方时，逐条回应其具体论点
4. 承认多方的合理观点——然后解释为什么这些不够充分
5. 如果证据确实转向看涨，诚实地调整你的信号

## 输出格式
返回**仅**一个 JSON 对象：
{
  "signal": "strong_buy|buy|hold|sell|strong_sell",
  "confidence": 0.0-1.0,
  "reasoning": "2-3句话，包含具体证据",
  "key_evidence": ["证据点1", "证据点2", "证据点3"],
  "technical_points": ["具体的看跌技术观察"],
  "risk_points": ["具体风险或担忧"]
}
"""

# Prompt for rebuttal rounds.
_REBUTTAL_INSTRUCTION = """\
## 当前辩论背景

上一轮产生了：

**对方论点：**
{opponent_summary}

**你之前的立场：**
{your_previous_summary}

**风险提示：**
{risk_comments}

## 你的任务
撰写反驳，要求：
1. 直接回应对方关键证据（逐条）
2. 用额外或重新解读的证据捍卫你的立场
3. 承认对方任何合理的观点
4. 如果证据确实改变了你的看法，更新你的信号

如果你认为对方的论证有说服力并改变了你的观点，请相应调整你的信号和置信度。目标是追求真相，而不是"赢得"辩论。
"""


class AdvocateAgent:
    """An advocate that argues bull or bear in structured debate."""

    def __init__(
        self,
        stance: str,  # "bull" or "bear"
        llm_adapter,
        config=None,
    ):
        self.stance = stance
        self.llm_adapter = llm_adapter
        self.config = config
        self.system_prompt = _BULL_SYSTEM_PROMPT if stance == "bull" else _BEAR_SYSTEM_PROMPT
        self.agent_name = f"{stance}_advocate"

    def argue(
        self,
        context_data: Dict[str, Any],
        stock_code: str,
        stock_name: str = "",
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        timeout: Optional[float] = None,
    ) -> "Argument":
        """Make an initial argument (Round 1)."""
        t0 = time.time()
        user_message = self._build_argument_prompt(context_data, stock_code, stock_name)

        try:
            if progress_callback:
                progress_callback({
                    "type": "debate_round",
                    "stage": self.stance,
                    "message": f"[{'多方' if self.stance == 'bull' else '空方'}] 正在构建初始论点...",
                })

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ]

            content = _stream_text_with_callback(
                self.llm_adapter, messages, progress_callback,
                f"[{'多方' if self.stance == 'bull' else '空方'}]",
                timeout=timeout,
                max_tokens=2048,
            )

            parsed = self._parse_json(content)

            if parsed:
                return Argument(
                    advocate=self.agent_name,
                    signal=parsed.get("signal", "hold"),
                    confidence=float(parsed.get("confidence", 0.5)),
                    reasoning=parsed.get("reasoning", ""),
                    key_evidence=parsed.get("key_evidence", []),
                    raw_data=parsed,
                )

        except Exception as exc:
            logger.error("[%s] argue failed: %s", self.agent_name, exc)

        return Argument(advocate=self.agent_name, signal="hold", confidence=0.5)

    def rebut(
        self,
        opponent_argument: "Argument",
        your_previous: Optional["Argument"],
        risk_comments: str = "",
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        timeout: Optional[float] = None,
    ) -> "Rebuttal":
        """Write a rebuttal in subsequent rounds."""
        t0 = time.time()

        opponent_summary = (
            f"信号: {opponent_argument.signal} (置信度: {opponent_argument.confidence:.2f})\n"
            f"理由: {opponent_argument.reasoning}\n"
            f"证据: {', '.join(opponent_argument.key_evidence[:3])}"
        )

        your_previous_summary = ""
        if your_previous:
            your_previous_summary = (
                f"你之前的信号: {your_previous.signal} (置信度: {your_previous.confidence:.2f})\n"
                f"你之前的理由: {your_previous.reasoning}"
            )

        instruction = _REBUTTAL_INSTRUCTION.format(
            opponent_summary=opponent_summary,
            your_previous_summary=your_previous_summary,
            risk_comments=risk_comments or "本轮无风险提示。",
        )

        try:
            if progress_callback:
                progress_callback({
                    "type": "debate_round",
                    "stage": self.stance,
                    "message": f"[{'多方' if self.stance == 'bull' else '空方'}] 正在反驳对方...",
                })

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": instruction},
            ]

            content = _stream_text_with_callback(
                self.llm_adapter, messages, progress_callback,
                f"[{'多方' if self.stance == 'bull' else '空方'}]",
                timeout=timeout,
                max_tokens=2048,
            )

            parsed = self._parse_json(content)

            if parsed:
                contested = []
                counter = parsed.get("key_evidence", [])

                return Rebuttal(
                    from_advocate=self.agent_name,
                    target_advocate=opponent_argument.advocate,
                    rebuttal_text=parsed.get("reasoning", ""),
                    contested_points=contested,
                    counter_evidence=counter,
                    revised_signal=parsed.get("signal"),
                    revised_confidence=float(parsed.get("confidence", 0.5)),
                )

        except Exception as exc:
            logger.error("[%s] rebut failed: %s", self.agent_name, exc)

        return Rebuttal(
            from_advocate=self.agent_name,
            target_advocate=opponent_argument.advocate,
        )

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _build_argument_prompt(
        self,
        context_data: Dict[str, Any],
        stock_code: str,
        stock_name: str = "",
    ) -> str:
        """Build the initial argument prompt from context data."""
        parts = [
            f"# 分析股票：{stock_code}",
        ]
        if stock_name:
            parts[-1] += f"（{stock_name}）"
        parts.append("")

        # Inject available data
        for key, value in context_data.items():
            if value is not None:
                if isinstance(value, dict):
                    parts.append(f"## {key}")
                    # Serialize dict as JSON
                    import json
                    parts.append(json.dumps(value, ensure_ascii=False, default=str))
                elif isinstance(value, list):
                    parts.append(f"## {key}")
                    for item in value:
                        parts.append(f"- {item}")
                else:
                    parts.append(f"## {key}")
                    parts.append(str(value))
                parts.append("")

        stance_desc = "看涨" if self.stance == "bull" else "看跌"
        parts.append(
            f"基于以上数据，为 {stock_code} 构建最有力的{stance_desc}论证。"
            f"用数据中的具体证据来支持你的论点。"
        )

        return "\n".join(parts)

    @staticmethod
    def _parse_json(text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON from LLM response."""
        import json
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except (json.JSONDecodeError, TypeError):
                pass

        return None
