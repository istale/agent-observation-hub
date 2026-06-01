# Evaluation Matrix

This matrix defines the intended division of responsibility. It is based on the project handoff and should be rechecked against each tool's current documentation before committing to a production integration.

| Capability | Agent Observation Hub | LiteLLM | Opik | Langfuse | Phoenix | Helicone | OpenTelemetry | OpenInference | OpenLLMetry |
|---|---|---|---|---|---|---|---|---|---|
| Gateway | Yes, observation gateway | Optional model gateway | No | No | No | Yes | No | No | No |
| Raw request/response storage | Yes, local raw archive | Possible logging/callbacks | Yes | Yes | Trace payloads | Yes | No, standard only | No, semantics only | Instrumentation dependent |
| Streaming capture | Yes, MVP JSONL chunks | Provider proxying/logging | Depends integration | Depends integration | Via spans/events | Yes | Via spans/events | Convention support | Instrumentation support |
| Self-host | Yes | Yes | Yes | Yes | Yes | Yes/hosted options | Yes | Yes | Yes |
| Redaction | Local recursive redaction | Config/callback dependent | Config dependent | Config dependent | Config dependent | Config dependent | Not built-in | Not built-in | Instrumentation/config dependent |
| Multi-user metadata | MVP headers | Routing/user metadata possible | Yes | Yes | Yes | Yes | Attributes | Semantic attributes | Attributes |
| Trace replay | Planned | Not core | Evaluation support | Evaluation support | Evaluation support | Limited/reference | No | No | No |
| Tool call spans | Planned | Not primary | Yes | Yes | Yes | Partial | Yes as spans | Yes | Yes |
| Agent-level spans | Planned/importers | No | Yes, including OpenClaw direction | Yes | Yes | Partial | Yes as spans | Yes | Yes |
| OpenTelemetry | Planned exporter | Integrations possible | Possible | Possible | Strong alignment | Possible | Native standard | Built on OTEL | Built on OTEL |
| OpenInference | Planned mapper | No | Possible | Possible | Strong alignment | No | No | Native convention | Related instrumentation |
| Evaluation | Planned harness | Routing/cost, not eval | Yes | Yes | Yes | Monitoring focused | No | No | No |
| Suitable for OpenClaw | Yes, local correlation layer | Optional model gateway | Yes, especially `opik-openclaw` | Possible | Possible | Possible | Standard layer | Semantic layer | Instrumentation reference |
| Suitable for Hermes | Yes, local raw observation | Optional model gateway | Possible exporter | Possible exporter | Possible exporter | Possible | Standard layer | Semantic layer | Instrumentation reference |
| Role in this architecture | Raw-local agent/session/channel observation | Optional provider adapter/model gateway | Backend/UI/eval candidate | Backend/UI/eval candidate | OpenInference viewer/eval candidate | Gateway/UI design reference | Vendor-neutral trace format | AI trace semantics | Instrumentation reference |

## Conclusions

- LiteLLM does not replace Agent Observation Hub.
- Agent Observation Hub does not require or replace LiteLLM. It owns raw-local observation, trace IDs, agent/session/channel/user correlation, and safe local archive.
- LiteLLM is optional. If production policy bans LiteLLM, AOH should point directly at an approved OpenAI-compatible upstream.
- Opik, Langfuse, and Phoenix are backend/UI/evaluation candidates, not required dependencies for Phase 1.
- OpenTelemetry and OpenInference are the standards layer for future export and interoperability.
- OpenLLMetry is a useful instrumentation reference, not a first-stage dependency.
- The Hub's core difference is local-first raw observation plus agent/session/channel/user correlation across OpenClaw, Hermes, optional model gateways, providers, and delivery channels.
