# Camel-AI Primary Debate Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CAMEL-AI the primary backend for `AGENT_ARCH=debate` while preserving the existing FinAgent interfaces and an internal rollback backend.

**Architecture:** Add a backend protocol at the current `DebateArena` boundary. Keep the existing arena behind `InternalDebateBackend`, add a lazy-loaded `CamelDebateBackend`, map both through the existing `DebateResult`, and select CAMEL only when the debate architecture is active.

**Tech Stack:** Python 3.10+, dataclasses/typing, CAMEL-AI `ChatAgent` and `ModelFactory`, existing LiteLLM configuration boundary, pytest/unittest, existing YAML/config registry.

## Global Constraints

- `AGENT_ARCH=single` and `AGENT_ARCH=multi` must not import or require CAMEL.
- `AGENT_ARCH=debate` selects CAMEL by default and supports `DEBATE_BACKEND=internal` rollback.
- CAMEL receives a bounded read-only FinAgent data snapshot; no ToolRegistry bridge is included in this change.
- `requirements-camel.txt` must constrain `mcp` to `<2.0.0` for CAMEL 0.2.90 compatibility.
- Public API, Web, Bot, Dashboard, and notification contracts remain backward compatible.
- New configuration must be documented in `.env.example`, the config registry, and `docs/CHANGELOG.md`.
- Do not add secrets, provider URLs, model names, or absolute paths to tracked files.

---

### Task 1: Add the backend protocol and normalized input contract

**Files:**
- Create: `src/agent/debate/backend.py`
- Create: `src/agent/debate/context_mapper.py`
- Test: `tests/test_camel_debate_backend.py`

**Interfaces:**
- Produces `DebateBackend`, `DebateInput`, and `build_debate_input()` for later backend implementations.
- `DebateBackend.debate(context, technical_opinion=None, intel_opinion=None, risk_opinion=None, progress_callback=None, timeout=None) -> DebateResult`.

- [ ] **Step 1: Write the failing contract tests**

```python
def test_debate_input_contains_only_bounded_serializable_context():
    context = AgentContext(query="分析 600519", stock_code="600519")
    context.set_data("news_context", {"items": ["x"]})
    context.set_data("runtime_object", object())

    payload = build_debate_input(context)

    assert payload.stock_code == "600519"
    assert payload.data["news_context"] == {"items": ["x"]}
    assert "runtime_object" not in payload.data
```

- [ ] **Step 2: Run the contract test and verify it fails**

Run: `python -m pytest tests/test_camel_debate_backend.py::test_debate_input_contains_only_bounded_serializable_context -q`

Expected: FAIL because `backend.py` and `context_mapper.py` do not exist.

- [ ] **Step 3: Implement the minimal protocol and mapper**

```python
@dataclass(frozen=True)
class DebateInput:
    stock_code: str
    stock_name: str
    data: Dict[str, Any]
    opinions: Dict[str, Optional[AgentOpinion]]


class DebateBackend(Protocol):
    def debate(self, context: AgentContext, technical_opinion=None,
               intel_opinion=None, risk_opinion=None,
               progress_callback=None, timeout=None) -> DebateResult: ...
```

The mapper must copy only JSON-compatible context fields, truncate long text fields to the configured snapshot limit, and keep opinions separate from raw data.

- [ ] **Step 4: Run the contract test and verify it passes**

Run: `python -m pytest tests/test_camel_debate_backend.py::test_debate_input_contains_only_bounded_serializable_context -q`

Expected: PASS.

### Task 2: Add optional CAMEL configuration and dependency boundary

**Files:**
- Create: `requirements-camel.txt`
- Modify: `src/config.py:540-550`
- Modify: `src/core/config_registry.py` near `AGENT_ARCH`
- Modify: `.env.example` near the debate settings
- Test: `tests/test_camel_debate_backend.py`

**Interfaces:**
- Produces config fields for backend selection, fallback, model platform/name, base URL, and API key.
- CAMEL values are parsed only as configuration; secrets remain sensitive and are never logged.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_debate_defaults_to_camel_backend(monkeypatch):
    monkeypatch.setenv("AGENT_ARCH", "debate")
    monkeypatch.delenv("DEBATE_BACKEND", raising=False)
    config = Config.from_env()
    assert config.debate_backend == "camel"
    assert config.debate_fallback_backend == "internal"


def test_single_architecture_does_not_require_camel_settings(monkeypatch):
    monkeypatch.setenv("AGENT_ARCH", "single")
    monkeypatch.delenv("CAMEL_API_KEY", raising=False)
    config = Config.from_env()
    assert config.agent_arch == "single"
```

- [ ] **Step 2: Run the tests and verify the expected failure**

Run: `python -m pytest tests/test_camel_debate_backend.py -k "backend or architecture" -q`

Expected: FAIL because the new config fields are not defined.

- [ ] **Step 3: Add optional dependency and configuration**

Add `camel-ai>=0.2.90,<0.3.0` and `mcp>=1.3.0,<2.0.0` to `requirements-camel.txt`, using the currently published 0.2.90 release as the compatibility floor and keeping the MCP 1.x API expected by CAMEL. Add config fields with defaults `camel`, `internal`, `openai_compatible`, empty model name, empty base URL, and empty API key. Add enum validation and sensitive registry metadata for the key.

- [ ] **Step 4: Run config and registry tests**

Run: `python -m pytest tests/test_camel_debate_backend.py tests/test_system_config_service.py -q`

Expected: PASS.

### Task 3: Implement the CAMEL model and response adapters

**Files:**
- Create: `src/agent/debate/camel_model_adapter.py`
- Create: `src/agent/debate/result_mapper.py`
- Test: `tests/test_camel_debate_backend.py`

**Interfaces:**
- `CamelModelAdapter.create(model_config) -> object` lazily imports CAMEL and returns a configured model backend.
- `map_camel_result(payload, input_data, rounds_completed, tokens_used) -> DebateResult`.

- [ ] **Step 1: Write failing mapper tests**

```python
def test_mapper_normalizes_signal_and_clamps_confidence():
    result = map_camel_result(
        {"final_signal": "strong_buy", "confidence": 1.8,
         "reasoning": "evidence", "consensus_reached": True},
        input_data=make_debate_input(), rounds_completed=2, tokens_used=40,
    )
    assert result.final_signal == "buy"
    assert result.final_confidence == 1.0
    assert result.rounds_completed == 2
```

- [ ] **Step 2: Run the mapper test and verify it fails**

Run: `python -m pytest tests/test_camel_debate_backend.py::test_mapper_normalizes_signal_and_clamps_confidence -q`

Expected: FAIL because `result_mapper.py` does not exist.

- [ ] **Step 3: Implement lazy model creation and strict result normalization**

Use the current CAMEL API shape: `ModelFactory.create(...)`, `ModelPlatformType.OPENAI_COMPATIBLE_MODEL`, and `ChatAgent(model=model, system_message=...)`. Keep the import inside the adapter method so non-debate modes do not import CAMEL. Reject missing API/model settings with a configuration error. Normalize `strong_buy`/`strong_sell` to `buy`/`sell`, clamp confidence, and default invalid output to `hold` with an error marker.

- [ ] **Step 4: Run mapper and adapter tests**

Run: `python -m pytest tests/test_camel_debate_backend.py -q`

Expected: PASS with fake CAMEL modules; no network calls.

### Task 4: Implement `CamelDebateBackend` and internal fallback

**Files:**
- Create: `src/agent/debate/camel_backend.py`
- Create: `src/agent/debate/internal_backend.py`
- Modify: `src/agent/debate/__init__.py`
- Test: `tests/test_camel_debate_backend.py`

**Interfaces:**
- `InternalDebateBackend` delegates to the current `DebateArena`.
- `CamelDebateBackend` creates bull, bear, risk, and moderator `ChatAgent`s and returns `DebateResult`.

- [ ] **Step 1: Write failing backend tests**

```python
def test_camel_backend_runs_roles_and_returns_normalized_result(fake_camel):
    backend = CamelDebateBackend(config=make_camel_config(), model_adapter=fake_camel)
    result = backend.debate(make_context())
    assert result.success is True
    assert result.final_signal in {"buy", "hold", "sell"}
    assert fake_camel.role_calls == ["bull", "bear", "risk", "moderator"]


def test_camel_backend_uses_internal_backend_on_execution_failure():
    fallback = MagicMock()
    fallback.debate.return_value = DebateResult(success=True, final_signal="hold")
    backend = CamelDebateBackend(config=make_camel_config(), fallback=fallback)
    result = backend.debate(make_context())
    assert result.success is True
    fallback.debate.assert_called_once()
```

- [ ] **Step 2: Run the backend tests and verify they fail**

Run: `python -m pytest tests/test_camel_debate_backend.py -k "camel_backend" -q`

Expected: FAIL because the backend classes do not exist.

- [ ] **Step 3: Implement the minimum role loop**

For each round, send the same serialized `DebateInput` plus prior round summary to bull, bear, and risk agents, then send their structured outputs to the moderator. Use one strict JSON correction retry per role, enforce the remaining timeout, emit the existing progress callback event types, and map the final response through `result_mapper.py`.

- [ ] **Step 4: Add internal delegation and fallback metadata**

`InternalDebateBackend` calls the existing `DebateArena.debate()`. The Camel backend catches only expected configuration, import, timeout, and response parsing failures, records `backend="camel"`, `fallback_used=True`, and delegates to the internal backend when enabled.

- [ ] **Step 5: Run the backend tests and verify they pass**

Run: `python -m pytest tests/test_camel_debate_backend.py -q`

Expected: PASS.

### Task 5: Wire Camel into `DebateOrchestrator` and the factory

**Files:**
- Modify: `src/agent/debate_orchestrator.py:212-235`
- Modify: `src/agent/factory.py:375-395`
- Test: `tests/test_camel_debate_backend.py`
- Test: `tests/test_agent_pipeline.py`

**Interfaces:**
- The outer orchestrator continues to call one backend method and keeps existing result conversion.
- The factory chooses Camel only for `agent_arch == "debate"`.

- [ ] **Step 1: Write failing factory isolation tests**

```python
def test_debate_factory_selects_camel_backend(monkeypatch):
    config = make_config(agent_arch="debate")
    executor = build_agent_executor(config)
    assert isinstance(executor.debate_backend, CamelDebateBackend)


def test_single_factory_does_not_import_camel(monkeypatch):
    config = make_config(agent_arch="single")
    build_agent_executor(config)
    assert "camel" not in sys.modules
```

- [ ] **Step 2: Run the isolation tests and verify failure**

Run: `python -m pytest tests/test_camel_debate_backend.py -k "factory" -q`

Expected: FAIL because the factory still constructs `DebateArena` directly.

- [ ] **Step 3: Wire backend selection**

Construct the backend in `_build_debate_orchestrator`, pass it into `DebateOrchestrator`, and replace the direct `DebateArena` construction with `self.debate_backend.debate(...)`. Keep the existing decision synthesis and Hermes persistence boundary unchanged.

- [ ] **Step 4: Run targeted integration tests**

Run: `python -m pytest tests/test_camel_debate_backend.py tests/test_agent_pipeline.py tests/test_multi_agent.py -q`

Expected: PASS.

### Task 6: Update documentation and governance records

**Files:**
- Modify: `.env.example` with the final CAMEL settings and rollback example
- Modify: `docs/LEARNING_PATH.md:153-162` to document `debate`
- Modify: `docs/CHANGELOG.md` with a flat `[Unreleased]` entry
- Create: `docs/debate-camel.md`

- [ ] **Step 1: Document runtime behavior**

Document installation through `requirements-camel.txt`, configuration, supported model endpoint, no-tool first version, fallback behavior, and the fact that `single`/`multi` are unchanged.

- [ ] **Step 2: Validate documentation references**

Run: `rg -n "DEBATE_BACKEND|CAMEL_MODEL|requirements-camel|AGENT_ARCH=debate" .env.example docs src tests`

Expected: every documented setting has a corresponding config field and implementation reference.

### Task 7: Verify the complete change

**Files:**
- No new files.

- [ ] **Step 1: Run targeted tests**

Run: `python -m pytest tests/test_camel_debate_backend.py tests/test_agent_pipeline.py tests/test_multi_agent.py -q`

- [ ] **Step 2: Run static checks and compilation**

Run: `python -m flake8 src/agent/debate src/agent/debate_orchestrator.py src/agent/factory.py tests/test_camel_debate_backend.py --count --select=E9,F63,F7,F82 --show-source --statistics`

Run: `python -m py_compile src/agent/debate/backend.py src/agent/debate/context_mapper.py src/agent/debate/camel_model_adapter.py src/agent/debate/result_mapper.py src/agent/debate/camel_backend.py src/agent/debate/internal_backend.py`

- [ ] **Step 3: Run the offline regression suite**

Run: `python -m pytest -m "not network" -q`

- [ ] **Step 4: Check the final diff and untracked files**

Run: `git diff --check; git status --short`

Expected: only Camel design, configuration, backend, documentation, and test files are changed; existing user media/scripts remain untracked and untouched.
