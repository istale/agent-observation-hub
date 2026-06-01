# Open Source Landscape

## Project Position

Agent Observation Hub is an Agent Observation Gateway plus Local Trace Store. It is not intended to become a full observability SaaS, model gateway replacement, or automatic optimization engine.

The priority is to capture enough local evidence to analyze agent and model behavior:

- user input
- agent run metadata
- context/prompt assembly
- final LLM request
- final LLM response
- streaming chunks
- tool call input/output/error
- channel delivery result
- session/user/agent/channel routing
- trace/run/LLM correlation IDs

## Model Gateway Layer

### LiteLLM

LiteLLM is an optional model gateway and provider adapter. Agent Observation Hub's required upstream contract is OpenAI-compatible HTTP, so production deployments can point AOH directly at an approved provider when LiteLLM is not installed, not approved, or banned.

Project strategy:

- Do not reimplement provider adapters in Agent Observation Hub.
- Place Hub in front of any approved OpenAI-compatible upstream.
- Use LiteLLM only when its gateway/routing behavior is allowed and useful.
- Capture Hub `llm_call_id` and map it to LiteLLM call IDs only when LiteLLM response headers are present.
- Use LiteLLM callbacks/logging as optional future inputs, never as required runtime dependencies.

## Observability Backend Layer

### Opik

Opik is a candidate backend for traces, monitoring, evaluation, datasets, and experiments. `opik-openclaw` is specifically relevant because it may provide native OpenClaw spans for LLM calls, sub-agents, tools, usage, and cost.

Project strategy:

- Do not require Opik for Phase 1.
- Add exporter support later.
- Evaluate `opik-openclaw` as a source of agent-level OpenClaw spans.

### Langfuse

Langfuse is a self-hostable LLM observability and evaluation backend.

Project strategy:

- Keep exporter disabled by default.
- Prefer self-hosted or redacted-only export mode.
- Never send raw sensitive local payloads to cloud by default.

### Phoenix

Phoenix is a strong candidate for OpenInference/OpenTelemetry trace viewing, troubleshooting, and evaluation.

Project strategy:

- Build OpenInference-like JSON preview first.
- Add OTEL/Phoenix export later.

### Helicone

Helicone combines LLM gateway and observability patterns.

Project strategy:

- Use as a design reference.
- Do not make Helicone or LiteLLM required in the MVP.

## Trace Standards and Instrumentation

### OpenTelemetry

OpenTelemetry is the vendor-neutral traces/metrics/logs standard.

Mapping target:

- `trace_runs` -> agent/chain span
- `llm_calls` -> LLM span
- `tool_calls` -> tool span
- retrieval events -> retriever span
- `trace_events` -> span events/logs

### OpenInference

OpenInference provides AI application semantic conventions on top of OpenTelemetry.

Project strategy:

- Align local names and structure so future export is smooth.
- Implement JSON preview before OTLP export.

### OpenLLMetry

OpenLLMetry is useful as an instrumentation reference for LLM observability on OpenTelemetry.

Project strategy:

- Reference its span and instrumentation patterns.
- Do not add it as a hard dependency in Phase 1.

## Evaluation Layer

Evaluation belongs after observation and correlation are stable. Candidate tools include Opik, Phoenix Evals, Langfuse Evals, TruLens, W&B Weave, and Braintrust.

Future local evaluation should support:

- trace replay
- failure classification
- prompt/model A/B comparison
- tool reliability evaluation
- context quality evaluation
- user correction/follow-up rate analysis
