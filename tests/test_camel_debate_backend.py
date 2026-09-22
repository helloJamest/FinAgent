"""Tests for the CAMEL-backed debate integration boundary."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agent.debate.backend import DebateInput
from src.agent.debate.context_mapper import build_debate_input
from src.agent.debate.result_mapper import map_camel_result
from src.agent.protocols import AgentContext, AgentOpinion


def make_context() -> AgentContext:
    context = AgentContext(query="分析 600519", stock_code="600519", stock_name="贵州茅台")
    context.set_data("news_context", {"items": ["业绩稳定"]})
    context.set_data("runtime_object", object())
    context.add_risk_flag("valuation", "估值偏高", severity="medium")
    return context


def make_debate_input() -> DebateInput:
    return build_debate_input(make_context())


def test_debate_input_contains_only_bounded_serializable_context():
    payload = build_debate_input(make_context())

    assert payload.stock_code == "600519"
    assert payload.data["news_context"] == {"items": ["业绩稳定"]}
    assert "runtime_object" not in payload.data
    assert payload.risk_flags[0]["category"] == "valuation"


def test_mapper_normalizes_signal_and_clamps_confidence():
    result = map_camel_result(
        {
            "final_signal": "strong_buy",
            "confidence": 1.8,
            "reasoning": "技术面和基本面均有证据支持。",
            "consensus_reached": True,
        },
        input_data=make_debate_input(),
        rounds_completed=2,
        tokens_used=40,
    )

    assert result.success is True
    assert result.final_signal == "buy"
    assert result.final_confidence == 1.0
    assert result.rounds_completed == 2
    assert result.tokens_used == 40


def test_mapper_rejects_non_mapping_result():
    with pytest.raises(ValueError, match="mapping"):
        map_camel_result([], input_data=make_debate_input())


def test_config_defaults_debate_to_camel_and_internal_fallback():
    from src.config import Config

    config = Config(agent_arch="debate")

    assert config.debate_backend == "camel"
    assert config.debate_fallback_backend == "internal"


def test_single_architecture_does_not_require_camel_settings():
    from src.config import Config

    config = Config(agent_arch="single")

    assert config.agent_arch == "single"


def test_camel_backend_runs_roles_and_returns_normalized_result(monkeypatch):
    from src.agent.debate.camel_backend import CamelDebateBackend

    calls = []

    class FakeAgent:
        def __init__(self, role):
            self.role = role

        def step(self, _message):
            calls.append(self.role)
            if self.role == "moderator":
                payload = '{"final_signal":"buy","confidence":0.7,"reasoning":"有效证据"}'
            else:
                payload = '{"signal":"buy","confidence":0.6,"reasoning":"证据"}'
            return SimpleNamespace(msg=SimpleNamespace(content=payload))

    class FakeAdapter:
        def create_agent(self, role, system_prompt):
            return FakeAgent(role)

    backend = CamelDebateBackend(
        config=SimpleNamespace(debate_max_rounds=1),
        model_adapter=FakeAdapter(),
    )
    result = backend.debate(make_context())

    assert result.success is True
    assert result.final_signal == "buy"
    assert calls == ["bull", "bear", "risk", "moderator"]


def test_camel_backend_uses_internal_backend_on_execution_failure():
    from src.agent.debate.camel_backend import CamelDebateBackend
    from src.agent.debate.debate_protocols import DebateResult

    fallback = MagicMock()
    fallback.debate.return_value = DebateResult(success=True, final_signal="hold")

    class BrokenAdapter:
        def create_agent(self, _role, _system_prompt):
            raise RuntimeError("camel unavailable")

    backend = CamelDebateBackend(
        config=SimpleNamespace(
            debate_max_rounds=1,
            debate_fallback_backend="internal",
        ),
        model_adapter=BrokenAdapter(),
        fallback=fallback,
    )

    result = backend.debate(make_context())

    assert result.success is True
    assert result.final_signal == "hold"
    fallback.debate.assert_called_once()


def test_non_debate_factory_does_not_import_camel(monkeypatch):
    from src.agent.factory import build_agent_executor

    monkeypatch.delitem(sys.modules, "camel", raising=False)
    config = SimpleNamespace(
        agent_arch="single",
        agent_max_steps=1,
        agent_orchestrator_timeout_s=1,
        agent_skills=[],
    )

    # The factory may import the regular agent stack, but it must not import
    # the optional CAMEL package for a non-debate architecture.
    try:
        build_agent_executor(config)
    except Exception:
        # This test is about optional-import isolation; other missing runtime
        # configuration is outside its scope.
        pass

    assert "camel" not in sys.modules


def test_debate_factory_selects_camel_backend(monkeypatch):
    import src.agent.factory as factory
    from src.agent.debate.camel_backend import CamelDebateBackend

    skill_manager = SimpleNamespace(get_skill_instructions=lambda: "")
    prompt_state = SimpleNamespace(
        skill_manager=skill_manager,
        skills_to_activate=[],
        explicit_skill_selection=False,
        use_legacy_default_prompt=False,
        skill_instructions="",
        default_skill_policy="",
        technical_skill_policy="",
    )
    config = SimpleNamespace(
        agent_arch="debate",
        agent_max_steps=1,
        agent_orchestrator_timeout_s=10,
        debate_backend="camel",
        debate_fallback_backend="internal",
        hermes_learning_enabled=False,
    )

    monkeypatch.setattr(factory, "get_tool_registry", lambda: MagicMock())
    monkeypatch.setattr(factory, "resolve_skill_prompt_state", lambda *_args, **_kwargs: prompt_state)

    executor = factory.build_agent_executor(config)

    assert isinstance(executor.debate_backend, CamelDebateBackend)
