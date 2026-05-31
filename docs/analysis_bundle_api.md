# Analysis Bundle API

## Purpose

`GET /api/traces/{trace_id}/analysis-bundle` returns a single structured package for local LLM agents, Codex, Hermes, or operators to analyze one agent/model run. It is an observation artifact, not an optimization engine.

The endpoint combines:

- trace run metadata
- agent/user/channel identity
- timeline events
- LLM call metadata
- request / response / stream payloads
- readable assistant and reasoning text
- external correlations
- diagnostics and warnings

## Endpoint

```text
GET /api/traces/{trace_id}/analysis-bundle
```

Missing trace:

```text
404 trace not found
```

## Payload Mode

The endpoint follows `AOH_PAYLOAD_MODE`.

```text
AOH_PAYLOAD_MODE=raw
```

Returns raw local request, response, and stream chunk payloads. This mode is intended for trusted local/company-internal LLM analysis.

```text
AOH_PAYLOAD_MODE=redacted
```

Returns redacted request, response, and stream chunk payloads.

Raw mode can expose Authorization headers, cookies, API keys, private prompts, user messages, agent memory, tool inputs/outputs, and file contents. Use redacted mode before sharing the hub, opening it to a network, or enabling cloud/exporter integrations.

## Response Shape

```json
{
  "trace_id": "trace_...",
  "payload_mode": "raw",
  "run": {},
  "identity": {
    "tenant_id": "local",
    "user_hash": "istale",
    "agent_id": "hermes",
    "session_id": "...",
    "channel": "discord",
    "conversation_id": "...",
    "identity_source": "ingress_route"
  },
  "timeline": [],
  "llm_calls": [
    {
      "metadata": {},
      "payloads": {
        "request": {},
        "response": {},
        "response_chunks": []
      },
      "derived": {
        "assistant_text": "...",
        "reasoning_text": "..."
      }
    }
  ],
  "correlations": [],
  "diagnostics": {
    "status": "ok",
    "has_raw_request": true,
    "has_response": true,
    "has_stream_chunks": false,
    "llm_call_count": 1,
    "event_count": 2,
    "correlation_count": 5,
    "warnings": []
  }
}
```

## Diagnostics

Warnings are used when the trace exists but some observation material is incomplete. For example:

```text
missing request payload: <payload_ref>
missing response payload: <payload_ref>
missing response chunks payload: <payload_ref>
no llm calls captured
```

Missing payload files do not fail the whole request. Invalid payload references that escape the raw archive still fail through the raw store path-safety checks.

## Example

```sh
curl http://127.0.0.1:43180/api/traces/<trace_id>/analysis-bundle
```
