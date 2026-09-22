# CAMEL Debate Backend

FinAgent uses CAMEL-AI as the primary orchestrator only when `AGENT_ARCH=debate`. The `single` and `multi` architectures keep their existing implementations and do not require the optional CAMEL dependency.

## Installation

Install the normal project dependencies first, then install the optional debate dependency. The optional requirements pin MCP to the 1.x API expected by CAMEL 0.2.90:

```bash
pip install -r requirements.txt
pip install -r requirements-camel.txt
```

## Configuration

Use an OpenAI-compatible model endpoint:

```env
AGENT_ARCH=debate
DEBATE_BACKEND=camel
DEBATE_FALLBACK_BACKEND=internal
CAMEL_MODEL_PLATFORM=openai_compatible
CAMEL_MODEL_NAME=<model-name>
CAMEL_BASE_URL=<https://provider.example/v1>
CAMEL_API_KEY=<api-key>
CAMEL_TEMPERATURE=0.1
CAMEL_MAX_TOKENS=4096
```

CAMEL receives the technical, intelligence, risk, and market data already collected by FinAgent as a bounded read-only snapshot. The first integration does not expose `ToolRegistry` or allow CAMEL to fetch additional data.

The debate roles are:

- Bull advocate
- Bear advocate
- Risk reviewer
- Moderator

The final response is normalized into FinAgent's existing `DebateResult` and dashboard contract. A CAMEL failure falls back to the original internal `DebateArena` when `DEBATE_FALLBACK_BACKEND=internal`.

## Rollback

To use the original debate implementation without changing `AGENT_ARCH`, set:

```env
DEBATE_BACKEND=internal
```

No database migration is required. Raw provider responses are not added to user-visible reports.
