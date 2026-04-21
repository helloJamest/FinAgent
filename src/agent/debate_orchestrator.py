# -*- coding: utf-8 -*-
"""
DebateOrchestrator — integrates DebateArena into the agent pipeline.

Presents the same ``run()`` / ``chat()`` interface as ``AgentOrchestrator``
so callers need no changes. The pipeline is:
  Technical → Intel → [Risk] → DebateArena → Decision Dashboard
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from src.agent.llm_adapter import LLMToolAdapter
from src.agent.protocols import (
    AgentContext,
    AgentOpinion,
    AgentRunStats,
    StageResult,
    StageStatus,
    normalize_decision_signal,
)
from src.agent.runner import parse_dashboard_json
from src.agent.tools.registry import ToolRegistry
from src.report_language import normalize_report_language

if TYPE_CHECKING:
    from src.agent.executor import AgentResult

logger = logging.getLogger(__name__)


@dataclass
class DebateOrchestratorResult:
    """Unified result from a debate pipeline run."""

    success: bool = False
    content: str = ""
    dashboard: Optional[Dict[str, Any]] = None
    tool_calls_log: List[Dict[str, Any]] = field(default_factory=list)
    total_steps: int = 0
    total_tokens: int = 0
    provider: str = ""
    model: str = ""
    error: Optional[str] = None
    stats: Optional[AgentRunStats] = None
    debate_result: Optional[Any] = None


class DebateOrchestrator:
    """Debate-mode orchestrator.

    Pipeline: Technical → Intel → [Risk] → DebateArena → Decision
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        llm_adapter: LLMToolAdapter,
        skill_instructions: str = "",
        technical_skill_policy: str = "",
        max_steps: int = 10,
        skill_manager=None,
        config=None,
        skill_memory=None,
        episode_store=None,
        debate_tracker=None,
    ):
        self.tool_registry = tool_registry
        self.llm_adapter = llm_adapter
        self.skill_instructions = skill_instructions
        self.technical_skill_policy = technical_skill_policy
        self.max_steps = max_steps
        self.skill_manager = skill_manager
        self.config = config
        self.skill_memory = skill_memory
        self.episode_store = episode_store
        self.debate_tracker = debate_tracker

    def _get_timeout_seconds(self) -> int:
        raw_value = getattr(self.config, "agent_orchestrator_timeout_s", 0)
        try:
            return max(0, int(raw_value or 0))
        except (TypeError, ValueError):
            return 0

    # -----------------------------------------------------------------
    # Public interface (mirrors AgentExecutor / AgentOrchestrator)
    # -----------------------------------------------------------------

    def run(self, task: str, context: Optional[Dict[str, Any]] = None) -> "AgentResult":
        from src.agent.executor import AgentResult

        ctx = self._build_context(task, context)
        ctx.meta["response_mode"] = "dashboard"
        result = self._execute_debate_pipeline(ctx, parse_dashboard=True)

        return AgentResult(
            success=result.success,
            content=result.content,
            dashboard=result.dashboard,
            tool_calls_log=result.tool_calls_log,
            total_steps=result.total_steps,
            total_tokens=result.total_tokens,
            provider=result.provider,
            model=result.model,
            error=result.error,
        )

    def chat(
        self,
        message: str,
        session_id: str,
        progress_callback: Optional[Callable] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> "AgentResult":
        from src.agent.executor import AgentResult
        from src.agent.conversation import conversation_manager

        ctx = self._build_context(message, context)
        ctx.session_id = session_id
        ctx.meta["response_mode"] = "chat"

        session = conversation_manager.get_or_create(session_id)
        history = session.get_history()
        if history:
            ctx.meta["conversation_history"] = history

        conversation_manager.add_message(session_id, "user", message)

        result = self._execute_debate_pipeline(ctx, parse_dashboard=False, progress_callback=progress_callback)

        if result.success:
            conversation_manager.add_message(session_id, "assistant", result.content)
        else:
            conversation_manager.add_message(
                session_id, "assistant",
                f"[分析失败] {result.error or '未知错误'}",
            )

        return AgentResult(
            success=result.success,
            content=result.content,
            dashboard=result.dashboard,
            tool_calls_log=result.tool_calls_log,
            total_steps=result.total_steps,
            total_tokens=result.total_tokens,
            provider=result.provider,
            model=result.model,
            error=result.error,
        )

    # -----------------------------------------------------------------
    # Pipeline execution
    # -----------------------------------------------------------------

    def _execute_debate_pipeline(
        self,
        ctx: AgentContext,
        parse_dashboard: bool = True,
        progress_callback: Optional[Callable] = None,
    ) -> DebateOrchestratorResult:
        """Run the debate pipeline: Technical → Intel → [Risk] → DebateArena."""
        stats = AgentRunStats()
        all_tool_calls: List[Dict[str, Any]] = []
        models_used: List[str] = []
        t0 = time.time()
        timeout_s = self._get_timeout_seconds()

        # Step 1: Technical analysis
        technical_opinion, tech_result = self._run_technical(ctx, progress_callback, timeout_s)
        stats.record_stage(tech_result)
        all_tool_calls.extend(tech_result.meta.get("tool_calls_log", []))
        models_used.extend(tech_result.meta.get("models_used", []))

        if not tech_result.success:
            return self._failure_result(stats, all_tool_calls, models_used, t0, "Technical analysis failed")

        elapsed_s = time.time() - t0
        if timeout_s and elapsed_s >= timeout_s:
            return self._timeout_result(stats, all_tool_calls, models_used, t0, timeout_s, ctx, parse_dashboard)

        # Step 2: Intel analysis
        intel_opinion, intel_result = self._run_intel(ctx, progress_callback, timeout_s)
        stats.record_stage(intel_result)
        all_tool_calls.extend(intel_result.meta.get("tool_calls_log", []))
        models_used.extend(intel_result.meta.get("models_used", []))

        if not intel_result.success:
            return self._failure_result(stats, all_tool_calls, models_used, t0, f"Intel analysis failed: {intel_result.error or 'unknown error'}")

        elapsed_s = time.time() - t0
        if timeout_s and elapsed_s >= timeout_s:
            return self._timeout_result(stats, all_tool_calls, models_used, t0, timeout_s, ctx, parse_dashboard)

        # Step 3: Risk analysis (optional, degrade gracefully)
        risk_opinion = None
        risk_result = None
        run_risk = getattr(self.config, "agent_orchestrator_mode", "standard") in ("full", "specialist")
        if run_risk:
            risk_opinion, risk_result = self._run_risk(ctx, progress_callback, timeout_s)
            if risk_result:
                stats.record_stage(risk_result)
                all_tool_calls.extend(risk_result.meta.get("tool_calls_log", []))
                models_used.extend(risk_result.meta.get("models_used", []))

        # Step 4: DebateArena
        from src.agent.debate import DebateArena

        arena = DebateArena(
            self.llm_adapter,
            config=self.config,
            skill_memory=self.skill_memory,
            episode_store=self.episode_store,
            debate_tracker=self.debate_tracker,
        )

        if progress_callback:
            progress_callback({"type": "stage_start", "stage": "debate", "message": "Starting multi-agent debate..."})

        debate_t0 = time.time()
        remaining_timeout = max(0.0, timeout_s - (time.time() - t0)) if timeout_s else None
        debate_result = arena.debate(
            ctx,
            technical_opinion=technical_opinion,
            intel_opinion=intel_opinion,
            risk_opinion=risk_opinion,
            progress_callback=progress_callback,
            timeout=remaining_timeout,
        )
        debate_duration = round(time.time() - debate_t0, 2)

        if progress_callback:
            progress_callback({"type": "stage_done", "stage": "debate", "status": "completed" if debate_result.success else "failed", "duration": debate_duration})

        elapsed_s = time.time() - t0
        stats.total_duration_s = round(elapsed_s, 2)
        stats.models_used = list(dict.fromkeys(models_used))

        if not debate_result.success:
            return DebateOrchestratorResult(
                success=False,
                error=f"Debate failed: {debate_result.error}",
                stats=stats,
                total_tokens=stats.total_tokens + debate_result.tokens_used,
                tool_calls_log=all_tool_calls,
                debate_result=debate_result,
            )

        # Step 5: Build final output
        dashboard = debate_result.dashboard
        content = ""
        if dashboard:
            content = json.dumps(dashboard, ensure_ascii=False, indent=2)
            ctx.set_data("final_dashboard", dashboard)
        elif debate_result.final_reasoning:
            content = debate_result.final_reasoning

        return DebateOrchestratorResult(
            success=bool(content),
            content=content,
            dashboard=dashboard,
            tool_calls_log=all_tool_calls,
            total_steps=stats.total_stages + debate_result.rounds_completed,
            total_tokens=stats.total_tokens + debate_result.tokens_used,
            provider=stats.models_used[0] if stats.models_used else "",
            model=", ".join(dict.fromkeys(models_used)),
            stats=stats,
            debate_result=debate_result,
        )

    # -----------------------------------------------------------------
    # Stage helpers
    # -----------------------------------------------------------------

    def _run_technical(
        self,
        ctx: AgentContext,
        progress_callback: Optional[Callable],
        timeout_s: int,
    ) -> tuple[Optional[AgentOpinion], StageResult]:
        from src.agent.agents.technical_agent import TechnicalAgent

        agent = TechnicalAgent(
            tool_registry=self.tool_registry,
            llm_adapter=self.llm_adapter,
            skill_instructions=self.skill_instructions,
            technical_skill_policy=self.technical_skill_policy,
        )
        agent.max_steps = min(agent.max_steps, self.max_steps)

        if progress_callback:
            progress_callback({"type": "stage_start", "stage": "technical", "message": "Starting technical analysis..."})

        remaining = max(0.0, timeout_s - (time.time() - (time.time()))) if timeout_s else None
        result = agent.run(ctx, progress_callback=progress_callback, timeout_seconds=remaining)

        if progress_callback:
            progress_callback({"type": "stage_done", "stage": "technical", "status": result.status.value, "duration": result.duration_s})

        return result.opinion, result

    def _run_intel(
        self,
        ctx: AgentContext,
        progress_callback: Optional[Callable],
        timeout_s: int,
    ) -> tuple[Optional[AgentOpinion], StageResult]:
        from src.agent.agents.intel_agent import IntelAgent

        agent = IntelAgent(
            tool_registry=self.tool_registry,
            llm_adapter=self.llm_adapter,
            skill_instructions=self.skill_instructions,
            technical_skill_policy=self.technical_skill_policy,
        )
        agent.max_steps = min(agent.max_steps, self.max_steps)

        if progress_callback:
            progress_callback({"type": "stage_start", "stage": "intel", "message": "Starting intel analysis..."})

        result = agent.run(ctx, progress_callback=progress_callback)

        if progress_callback:
            progress_callback({"type": "stage_done", "stage": "intel", "status": result.status.value, "duration": result.duration_s})

        return result.opinion, result

    def _run_risk(
        self,
        ctx: AgentContext,
        progress_callback: Optional[Callable],
        timeout_s: int,
    ) -> tuple[Optional[AgentOpinion], StageResult]:
        from src.agent.agents.risk_agent import RiskAgent

        agent = RiskAgent(
            tool_registry=self.tool_registry,
            llm_adapter=self.llm_adapter,
            skill_instructions=self.skill_instructions,
            technical_skill_policy=self.technical_skill_policy,
        )
        agent.max_steps = min(agent.max_steps, self.max_steps)

        if progress_callback:
            progress_callback({"type": "stage_start", "stage": "risk", "message": "Starting risk analysis..."})

        result = agent.run(ctx, progress_callback=progress_callback)

        if progress_callback:
            progress_callback({"type": "stage_done", "stage": "risk", "status": result.status.value, "duration": result.duration_s})

        return result.opinion, result

    # -----------------------------------------------------------------
    # Result builders
    # -----------------------------------------------------------------

    @staticmethod
    def _failure_result(stats, tool_calls, models, t0, error: str) -> DebateOrchestratorResult:
        stats.total_duration_s = round(time.time() - t0, 2)
        stats.models_used = list(dict.fromkeys(models))
        return DebateOrchestratorResult(
            success=False,
            error=error,
            stats=stats,
            total_tokens=stats.total_tokens,
            tool_calls_log=tool_calls,
        )

    def _timeout_result(
        self, stats, tool_calls, models, t0, timeout_s: int,
        ctx: AgentContext, parse_dashboard: bool,
    ) -> DebateOrchestratorResult:
        elapsed = round(time.time() - t0, 2)
        stats.total_duration_s = elapsed
        stats.models_used = list(dict.fromkeys(models))
        error = f"Pipeline timed out after {elapsed}s (limit: {timeout_s}s)"
        return DebateOrchestratorResult(
            success=False,
            error=error,
            stats=stats,
            total_tokens=stats.total_tokens,
            tool_calls_log=tool_calls,
        )

    # -----------------------------------------------------------------
    # Context building
    # -----------------------------------------------------------------

    def _build_context(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentContext:
        ctx = AgentContext(query=task)

        if context:
            ctx.stock_code = context.get("stock_code", "")
            ctx.stock_name = context.get("stock_name", "")
            requested_skills = context.get("skills")
            if requested_skills is None:
                requested_skills = context.get("strategies", [])
            ctx.meta["skills_requested"] = requested_skills or []
            ctx.meta["strategies_requested"] = requested_skills or []
            ctx.meta["report_language"] = normalize_report_language(context.get("report_language", "zh"))

            for data_key in ("realtime_quote", "daily_history", "chip_distribution",
                             "trend_result", "news_context"):
                if context.get(data_key):
                    ctx.set_data(data_key, context[data_key])

        if not ctx.stock_code:
            ctx.stock_code = _extract_stock_code(task)

        if "report_language" not in ctx.meta:
            ctx.meta["report_language"] = "zh"

        return ctx


# -----------------------------------------------------------------
# Helpers (reused from orchestrator.py)
# -----------------------------------------------------------------

_COMMON_WORDS: set[str] = {
    "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL",
    "CAN", "HAD", "HER", "WAS", "ONE", "OUR", "OUT", "HAS",
    "HIS", "HOW", "ITS", "LET", "MAY", "NEW", "NOW", "OLD",
    "SEE", "WAY", "WHO", "DID", "GET", "HIM", "USE", "SAY",
    "SHE", "TOO", "ANY", "WITH", "FROM", "THAT", "THAN",
    "THIS", "WHAT", "WHEN", "WILL", "JUST", "ALSO",
    "BEEN", "EACH", "HAVE", "MUCH", "ONLY", "OVER",
    "SOME", "SUCH", "THEM", "THEN", "THEY", "VERY",
    "WERE", "YOUR", "ABOUT", "AFTER", "COULD", "EVERY",
    "OTHER", "THEIR", "THERE", "THESE", "THOSE", "WHICH",
    "WOULD", "BEING", "STILL", "WHERE",
    "BUY", "SELL", "HOLD", "LONG", "PUT", "CALL",
    "ETF", "IPO", "RSI", "EPS", "PEG", "ROE", "ROA",
    "USA", "USD", "CNY", "HKD", "EUR", "GBP",
    "STOCK", "TRADE", "PRICE", "INDEX", "FUND",
    "HIGH", "LOW", "OPEN", "CLOSE", "STOP", "LOSS",
    "TREND", "BULL", "BEAR", "RISK", "CASH", "BOND",
    "MACD", "VWAP", "BOLL",
    "HELLO", "PLEASE", "THANKS", "CHECK", "LOOK", "THINK",
    "MAYBE", "GUESS", "TELL", "SHOW", "WHAT", "WHATS",
    "WHY", "WHEN", "HOWDY", "HEY", "HI",
}

_LOWERCASE_TICKER_HINTS = re.compile(
    r"分析|看看|查一?下|研究|诊断|走势|趋势|股价|股票|个股",
)


def _extract_stock_code(text: str) -> str:
    """Best-effort stock code extraction from free text."""
    m = re.search(r'(?<!\d)((?:[03648]\d{5}|92\d{4}))(?!\d)', text)
    if m:
        return m.group(1)
    m = re.search(r'(?<![a-zA-Z])(hk\d{5})(?!\d)', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.search(r'(?<![a-zA-Z])([A-Z]{2,5}(?:\.[A-Z]{1,2})?)(?![a-zA-Z])', text)
    if m:
        candidate = m.group(1)
        if candidate not in _COMMON_WORDS:
            return candidate

    stripped = (text or "").strip()
    bare_match = re.fullmatch(r'([A-Za-z]{2,5}(?:\.[A-Za-z]{1,2})?)', stripped)
    if bare_match:
        candidate = bare_match.group(1).upper()
        if candidate not in _COMMON_WORDS:
            return candidate

    if not _LOWERCASE_TICKER_HINTS.search(stripped):
        return ""

    for match in re.finditer(r'(?<![a-zA-Z])([A-Za-z]{2,5}(?:\.[A-Za-z]{1,2})?)(?![a-zA-Z])', text):
        raw_candidate = match.group(1)
        candidate = raw_candidate.upper()
        if candidate in _COMMON_WORDS:
            continue
        return candidate
    return ""
