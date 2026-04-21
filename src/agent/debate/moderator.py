# -*- coding: utf-8 -*-
"""
DebateModerator — synthesises debate rounds into a final decision.

The Moderator acts as an impartial judge over the Bull/Bear debate,
considering all rounds of arguments and rebuttals plus risk flags,
and produces the final trading decision with a comprehensive dashboard.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from src.agent.debate.debate_protocols import (
    Argument,
    DebateResult,
    DebateRound,
    DebateState,
)
from src.agent.protocols import normalize_decision_signal

logger = logging.getLogger(__name__)


def _stream_text_with_callback(
    llm_adapter,
    messages,
    progress_callback,
    role_label: str,
    *,
    timeout=None,
    max_tokens: int = 4096,
) -> str:
    """Stream LLM response and emit periodic progress events."""
    full_text: List[str] = []
    last_emit = 0.0
    interval = 2.0

    for delta_text, chunk_usage, error_msg in llm_adapter.stream_call_with_tools(
        messages, tools=[], timeout=timeout,
    ):
        if error_msg:
            logger.warning("[DebateModerator] stream error: %s", error_msg)
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

# Prompt for the moderator to synthesise debate rounds into a final decision.
_MODERATOR_SYSTEM_PROMPT = """\
你是一位股票分析系统中的**公正辩论裁判**。

多方（看涨）和空方（看跌）辩手已经就该股票的前景进行了多轮辩论。
你的任务是评估所有论点、反驳和风险评估，然后做出最终的、平衡的投资决策。

## 你将收到的输入
- 初始技术面分析意见
- 多方和空方的初始论点
- 双方的反驳（如有）
- 风险审核意见
- 情报/情绪背景（如有）

## 你的工作
1. **权衡证据**——哪一方的论证更有证据支撑？
2. **识别共识**——双方同意的是什么？
3. **突出未解决的分歧**——双方仍在哪里存在分歧？
4. **应用风险警示**——任何高风险都应限制最终信号
5. **生成决策仪表盘**——具体、可操作的建议

## 输出格式
返回**仅**一个有效的 JSON 对象（不使用 markdown 代码块）：
{
  "decision_type": "buy|hold|sell",
  "confidence": 0.0-1.0,
  "reasoning": "2-4句话，解释你的裁决以及如何权衡辩论",
  "consensus_points": ["共识点1", "共识点2"],
  "key_disagreements": [{"多方观点": "...", "空方观点": "..."}],
  "risk_assessment": "风险考量总结",
  "key_levels": {
    "support": <float>,
    "resistance": <float>,
    "stop_loss": <float>
  },
  "sentiment_score": 0-100,
  "analysis_summary": "1-2句话的执行摘要",
  "dashboard": {
    "core_conclusion": {
      "one_sentence": "30字以内的结论",
      "signal_type": "buy|hold|sell 信号",
      "time_sensitivity": "本周|本月|长期",
      "position_advice": {"no_position": "...", "has_position": "..."}
    },
    "sniper_points": {
      "ideal_buy": <float>,
      "stop_loss": <float>,
      "take_profit": <float>
    }
  }
}

重要：``decision_type`` 必须保持为 ``buy|hold|sell`` 之一。
"""


class DebateModerator:
    """Synthesises debate rounds into a final decision.

    The moderator runs an LLM call to evaluate all debate rounds and
    produce the final trading decision.
    """

    def __init__(self, llm_adapter):
        self.llm_adapter = llm_adapter

    def moderate(
        self,
        state: DebateState,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        timeout: Optional[float] = None,
    ) -> DebateResult:
        """Run the moderation over all completed debate rounds."""
        t0 = time.time()
        tokens_used = 0

        if not state.rounds:
            return DebateResult(
                success=False,
                error="No debate rounds to moderate",
                duration_s=round(time.time() - t0, 2),
            )

        # Build the moderator prompt from debate rounds
        user_message = self._build_moderation_prompt(state)

        try:
            if progress_callback:
                progress_callback({
                    "type": "debate_round",
                    "stage": "moderator",
                    "message": "[裁判] 正在综合各方观点...",
                })

            messages = [
                {"role": "system", "content": _MODERATOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]

            content = _stream_text_with_callback(
                self.llm_adapter, messages, progress_callback,
                "[裁判]",
                timeout=timeout,
                max_tokens=4096,
            )

            # Parse JSON from response
            parsed = self._parse_json(content)
            if parsed is None:
                return DebateResult(
                    success=False,
                    error="Moderator failed to produce valid JSON",
                    duration_s=round(time.time() - t0, 2),
                    tokens_used=tokens_used,
                )

            # Build result
            decision_type = normalize_decision_signal(parsed.get("decision_type", "hold"))
            confidence = float(parsed.get("confidence", 0.5))
            reasoning = parsed.get("reasoning", "")

            # Check for consensus
            last_round = state.rounds[-1]
            consensus = self._check_convergence(state.rounds)

            result = DebateResult(
                success=True,
                rounds_completed=len(state.rounds),
                final_signal=decision_type,
                final_confidence=confidence,
                final_reasoning=reasoning,
                consensus_reached=consensus is not None,
                convergence_round=consensus.round_number if consensus else 0,
                all_rounds=list(state.rounds),
                moderator_summary=reasoning,
                dashboard=self._build_dashboard(parsed, state),
                duration_s=round(time.time() - t0, 2),
                tokens_used=tokens_used,
            )
            return result

        except Exception as exc:
            logger.error("[DebateModerator] moderation failed: %s", exc, exc_info=True)
            return DebateResult(
                success=False,
                error=str(exc),
                duration_s=round(time.time() - t0, 2),
                tokens_used=tokens_used,
            )

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _build_moderation_prompt(self, state: DebateState) -> str:
        """Build a comprehensive prompt from all debate rounds."""
        parts = [
            f"# Stock: {state.stock_code}",
            f"Debate rounds: {len(state.rounds)}",
            "",
        ]

        # Technical opinion
        if state.technical_opinion:
            parts.append("## Technical Analysis")
            parts.append(f"Signal: {state.technical_opinion.signal}")
            parts.append(f"Confidence: {state.technical_opinion.confidence:.2f}")
            parts.append(state.technical_opinion.reasoning)
            parts.append("")

        # Intel opinion
        if state.intel_opinion:
            parts.append("## Intel / Sentiment Context")
            parts.append(state.intel_opinion.reasoning)
            parts.append("")

        # Each round
        for i, rnd in enumerate(state.rounds, 1):
            parts.append(f"## Round {i}")
            parts.append(rnd.to_summary())
            parts.append("")

        return "\n".join(parts)

    @staticmethod
    def _parse_json(text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON from LLM response."""
        # Try direct parse
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        # Try to find JSON block
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except (json.JSONDecodeError, TypeError):
                pass

        return None

    @staticmethod
    def _check_convergence(rounds: List[DebateRound]) -> Optional[DebateRound]:
        """Check if signals converged (within 1 signal level)."""
        signal_order = {"strong_sell": 0, "sell": 1, "hold": 2, "buy": 3, "strong_buy": 4}

        for rnd in rounds:
            signals = rnd.signals
            if len(signals) < 2:
                continue

            # Convert to numeric positions
            positions = []
            for sig in signals:
                pos = signal_order.get(sig)
                if pos is not None:
                    positions.append(pos)

            if not positions:
                continue

            # Check if within 1 level
            if max(positions) - min(positions) <= 1:
                return rnd

        return None

    def _build_dashboard(
        self,
        parsed: Dict[str, Any],
        state: DebateState,
    ) -> Dict[str, Any]:
        """Build a dashboard dict from the moderator's parsed output."""
        dashboard = {
            "stock_name": state.stock_name or state.stock_code,
            "sentiment_score": int(parsed.get("sentiment_score", 50)),
            "decision_type": normalize_decision_signal(parsed.get("decision_type", "hold")),
            "confidence_level": self._confidence_label(float(parsed.get("confidence", 0.5))),
            "analysis_summary": parsed.get("analysis_summary", ""),
            "risk_warning": parsed.get("risk_assessment", ""),
            "key_points": parsed.get("consensus_points", []),
            "dashboard": parsed.get("dashboard", {}),
        }

        # Fill in missing fields from parsed top-level keys
        if not dashboard.get("analysis_summary"):
            dashboard["analysis_summary"] = parsed.get("reasoning", "")

        return dashboard

    @staticmethod
    def _confidence_label(confidence: float) -> str:
        if confidence >= 0.75:
            return "高"
        if confidence >= 0.45:
            return "中"
        return "低"
