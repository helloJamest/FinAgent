# Camel-AI Primary Debate Backend Design

## Goal

Make CAMEL-AI the primary orchestration framework for `AGENT_ARCH=debate` while preserving FinAgent's existing data pipeline, model configuration boundary, dashboard contract, and rollback path. `single` and `multi` architectures remain unchanged.

## Scope

Included:

- A `DebateBackend` protocol shared by the existing and CAMEL implementations.
- A `CamelDebateBackend` that orchestrates bull, bear, risk, and moderator roles.
- Conversion between FinAgent's `AgentContext`/`AgentOpinion` objects and a read-only debate snapshot.
- Conversion from CAMEL responses to the existing `DebateResult` and dashboard contract.
- Lazy CAMEL imports and an optional dependency file so `single` and `multi` do not require CAMEL.
- Configurable timeout, round, token, and fallback behavior.
- Offline tests using fake CAMEL modules and deterministic model responses.

Excluded:

- Replacing `AGENT_ARCH=single` or `AGENT_ARCH=multi`.
- Giving CAMEL direct access to FinAgent's `ToolRegistry` in the first implementation.
- Adding browser, computer-use, MCP, or autonomous external actions.
- Changing the public API, Web payload, Bot commands, report schema, or notification formats.
- Replacing the existing LiteLLM provider configuration for non-debate modes.

## Existing Integration Boundary

The current `DebateOrchestrator` already runs technical, intelligence, optional risk, debate, and decision stages. The new backend is inserted only at the debate stage. The outer orchestrator continues to own progress callbacks, total timeout accounting, Hermes persistence, and final DecisionAgent synthesis.

```text
TechnicalAgent -> IntelAgent -> RiskAgent?
                              |
                              v
                    DebateBackend.debate()
                              |
                DebateResult + normalized dashboard
                              |
                              v
                    existing DecisionAgent
```

## Components

### `DebateBackend`

The protocol accepts an `AgentContext`, the technical/intelligence/risk opinions, a progress callback, and a remaining timeout. It returns the existing `DebateResult`. The protocol keeps the backend replaceable without exposing CAMEL types to callers.

### `InternalDebateBackend`

Wraps the existing `DebateArena` unchanged. It is retained for rollback, deterministic comparison tests, and environments where CAMEL is unavailable.

### `CamelDebateBackend`

Creates four CAMEL `ChatAgent` instances:

- Bull advocate: constructs a positive thesis from the supplied evidence.
- Bear advocate: constructs a negative thesis and attacks unsupported assumptions.
- Risk reviewer: identifies downside, data quality, and uncertainty risks.
- Moderator: produces the final signal, confidence, reasoning, convergence status, and dashboard fields.

The backend passes a bounded, JSON-serializable snapshot to each agent. The first version runs one complete round at a time, limits the number of rounds, and does not register external tools. This keeps inputs identical to the internal backend and prevents duplicate data-provider calls.

### `CamelModelAdapter`

Builds CAMEL model backends from explicit FinAgent configuration. The preferred path is an OpenAI-compatible endpoint so the same model endpoint can be used in comparison runs. Provider-specific CAMEL configuration remains isolated behind this adapter. Model creation is lazy and raises a clear configuration error only when `AGENT_ARCH=debate` selects CAMEL.

### Mappers

`context_mapper` produces a bounded `DebateInput` snapshot. `result_mapper` validates CAMEL JSON, normalizes signals to the existing `buy|hold|sell` contract, clamps confidence to `[0, 1]`, preserves round summaries, and creates a dashboard compatible with the existing DecisionAgent and API consumers.

## Configuration

The default architecture remains `single`. When `AGENT_ARCH=debate`, CAMEL is the primary backend:

```env
AGENT_ARCH=debate
DEBATE_BACKEND=camel
DEBATE_FALLBACK_BACKEND=internal
CAMEL_MODEL_PLATFORM=openai_compatible
CAMEL_MODEL_NAME=<provider model name>
CAMEL_BASE_URL=<OpenAI-compatible endpoint>
CAMEL_API_KEY=<provider key>
```

`DEBATE_BACKEND=internal` is a supported rollback and comparison switch. `DEBATE_FALLBACK_BACKEND=internal` is used only after a CAMEL initialization or execution failure and is reported in the result metadata. CAMEL settings are not read or validated for `single` and `multi`.

The dependency is kept in `requirements-camel.txt`; the base `requirements.txt` does not gain a mandatory CAMEL dependency. The optional file pins `mcp<2.0.0` because CAMEL 0.2.90 imports `FastMCP` from the MCP 1.x namespace. Docker and CI can opt into the dependency for the debate-specific test/build job.

## Failure and Timeout Behavior

- A missing optional dependency produces a clear error naming `requirements-camel.txt`.
- Invalid CAMEL model settings fail before the first debate round.
- Each round receives the remaining outer orchestration timeout.
- Malformed agent output is retried once with a strict JSON correction prompt; a second malformed response fails the CAMEL backend.
- CAMEL failure uses the configured internal fallback when enabled.
- If both backends fail, the existing outer failure result is returned without leaking provider details to API clients.
- CAMEL output is never allowed to bypass the existing risk override or dashboard validation.

## Observability

The backend emits the existing stage progress events with `stage="debate"`, plus backend name, rounds completed, token count, duration, fallback usage, and parse status in internal metadata. Raw provider responses are not persisted in the user-visible report.

## Testing Strategy

- Protocol tests prove both backends satisfy the same result contract.
- Mapper tests cover valid output, malformed JSON, invalid signals, confidence clamping, missing dashboard fields, and oversized evidence truncation.
- CAMEL backend tests install fake `camel` modules in `sys.modules`, so normal CI does not require network access or API keys.
- Factory tests prove `single` and `multi` do not import CAMEL, while `debate` selects the CAMEL backend by default.
- Fallback tests prove CAMEL initialization and execution failures use the internal backend when configured.
- Existing multi-agent and offline test suites remain mandatory.

## Rollout and Rollback

The change is activated only by `AGENT_ARCH=debate`. Existing deployments continue using `single` unless explicitly changed. To roll back debate orchestration without reverting code, set:

```env
DEBATE_BACKEND=internal
```

If the optional package is unavailable, use the same setting or install `requirements-camel.txt`. No database migration is required.
