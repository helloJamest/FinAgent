"""CAMEL-AI debate backend for the debate architecture."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from typing import Any, Callable, Dict, Optional

from src.agent.debate.backend import DebateInput
from src.agent.debate.context_mapper import build_debate_input
from src.agent.debate.debate_protocols import Argument, DebateResult, DebateRound
from src.agent.debate.result_mapper import map_camel_result
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json

logger = logging.getLogger(__name__)

_ROLE_PROMPTS = {
    "bull": "你是股票分析中的多方辩手，只能基于给定证据提出看涨论点。输出严格 JSON。",
    "bear": "你是股票分析中的空方辩手，只能基于给定证据提出看跌论点。输出严格 JSON。",
    "risk": "你是独立风险审查员，识别证据缺口、下行风险和不确定性。输出严格 JSON。",
    "moderator": "你是公正的股票辩论裁判，综合多空和风险意见，输出严格 JSON。",
}


class CamelDebateBackend:
    """Run the debate stage through CAMEL ChatAgents."""

    def __init__(self, config=None, model_adapter=None, fallback=None):
        self.config = config
        self.model_adapter = model_adapter
        self.fallback = fallback
        self.max_rounds = max(1, int(getattr(config, "debate_max_rounds", 3)))

    def _get_model_adapter(self):
        if self.model_adapter is None:
            from src.agent.debate.camel_model_adapter import CamelModelAdapter

            self.model_adapter = CamelModelAdapter(self.config)
        return self.model_adapter

    @staticmethod
    def _response_text(response: Any) -> str:
        message = getattr(response, "msg", None)
        if message is not None and getattr(message, "content", None):
            return str(message.content)
        messages = getattr(response, "msgs", None) or []
        if messages and getattr(messages[0], "content", None):
            return str(messages[0].content)
        if isinstance(response, str):
            return response
        return ""

    def _ask_json(self, agent: Any, prompt: str, role: str, progress_callback=None) -> Dict[str, Any]:
        if progress_callback:
            progress_callback({"type": "debate_round", "stage": role, "message": f"[{role}] CAMEL 正在生成..."})
        parsed = try_parse_json(self._response_text(agent.step(prompt)))
        if parsed is None:
            correction = "请将上一条回复改写为一个不带 Markdown 代码块的有效 JSON 对象，只返回 JSON。"
            parsed = try_parse_json(self._response_text(agent.step(correction)))
        if not isinstance(parsed, dict):
            raise ValueError(f"CAMEL {role} response is not valid JSON")
        return parsed

    @staticmethod
    def _serialize_input(input_data: DebateInput) -> str:
        opinions = {
            name: asdict(opinion) if isinstance(opinion, AgentOpinion) else None
            for name, opinion in input_data.opinions.items()
        }
        return json.dumps(
            {
                "query": input_data.query,
                "stock_code": input_data.stock_code,
                "stock_name": input_data.stock_name,
                "data": input_data.data,
                "opinions": opinions,
                "risk_flags": input_data.risk_flags,
            },
            ensure_ascii=False,
            default=str,
        )

    @staticmethod
    def _argument(role: str, payload: Dict[str, Any]) -> Argument:
        confidence = payload.get("confidence", 0.5)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.5
        evidence = payload.get("key_evidence", payload.get("evidence", []))
        if not isinstance(evidence, list):
            evidence = [str(evidence)] if evidence else []
        return Argument(
            advocate=f"{role}_advocate",
            signal=str(payload.get("signal", "hold")),
            confidence=confidence,
            reasoning=str(payload.get("reasoning", "") or ""),
            key_evidence=[str(item) for item in evidence[:5]],
            raw_data=payload,
        )

    def debate(
        self,
        context: AgentContext,
        technical_opinion: Optional[AgentOpinion] = None,
        intel_opinion: Optional[AgentOpinion] = None,
        risk_opinion: Optional[AgentOpinion] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        timeout: Optional[float] = None,
    ) -> DebateResult:
        started = time.monotonic()
        try:
            input_data = build_debate_input(
                context,
                technical=technical_opinion,
                intel=intel_opinion,
                risk=risk_opinion,
            )
            adapter = self._get_model_adapter()
            agents = {role: adapter.create_agent(role, prompt) for role, prompt in _ROLE_PROMPTS.items()}
            serialized_input = self._serialize_input(input_data)
            rounds = []
            moderator_payload: Dict[str, Any] = {}

            for round_number in range(1, self.max_rounds + 1):
                if timeout and time.monotonic() - started >= timeout:
                    raise TimeoutError("CAMEL debate timed out before the next round")
                prior = json.dumps([asdict(item) for item in rounds[-2:]], ensure_ascii=False, default=str)
                common = f"股票输入快照：\n{serialized_input}\n上一轮摘要：\n{prior}"
                bull_payload = self._ask_json(agents["bull"], common, "bull", progress_callback)
                bear_payload = self._ask_json(agents["bear"], common, "bear", progress_callback)
                risk_payload = self._ask_json(
                    agents["risk"],
                    f"{common}\n多方：{json.dumps(bull_payload, ensure_ascii=False)}\n空方：{json.dumps(bear_payload, ensure_ascii=False)}",
                    "risk",
                    progress_callback,
                )
                current_round = DebateRound(
                    round_number=round_number,
                    bull_argument=self._argument("bull", bull_payload),
                    bear_argument=self._argument("bear", bear_payload),
                    risk_comment=self._argument("risk", risk_payload),
                )
                rounds.append(current_round)
                moderator_payload = self._ask_json(
                    agents["moderator"],
                    f"{common}\n当前辩论轮次：{json.dumps(asdict(current_round), ensure_ascii=False, default=str)}\n"
                    "请输出 final_signal、confidence、reasoning、consensus_reached、dashboard。",
                    "moderator",
                    progress_callback,
                )
                if moderator_payload.get("consensus_reached") or moderator_payload.get("converged"):
                    break

            result = map_camel_result(
                moderator_payload,
                input_data=input_data,
                rounds_completed=len(rounds),
            )
            result.all_rounds = rounds
            result.backend = "camel"
            return result
        except Exception as exc:
            logger.warning("[CamelDebateBackend] CAMEL debate failed: %s", exc)
            if self.fallback is not None and getattr(self.config, "debate_fallback_backend", "internal") == "internal":
                result = self.fallback.debate(
                    context,
                    technical_opinion=technical_opinion,
                    intel_opinion=intel_opinion,
                    risk_opinion=risk_opinion,
                    progress_callback=progress_callback,
                    timeout=timeout,
                )
                result.fallback_used = True
                result.backend = "internal"
                return result
            return DebateResult(success=False, backend="camel", error="CAMEL debate failed")
