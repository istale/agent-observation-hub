# User Analysis Bundle API

## Purpose

`GET /api/subjects/users/{user_hash}/analysis-bundle` returns a user-centered observation package for local LLM analysis. It is meant for questions such as:

- What has this user recently asked Hermes or OpenClaw to do?
- Which traces should we inspect deeply?
- Are there repeated latency, token, routing, or response-shape patterns?
- Which trace IDs should be passed to `/api/traces/{trace_id}/analysis-bundle`?

This endpoint sits above the per-trace analysis bundle. It is a discovery and behavior-analysis bundle, not an optimizer.

## Endpoint

```text
GET /api/subjects/users/{user_hash}/analysis-bundle
```

Query parameters:

- `limit`: maximum traces to include. Default `10`.
- `days`: only include traces started within the last N days.
- `agent_id`: optional agent filter, such as `hermes`.
- `channel`: optional channel filter, such as `discord`.
- `status`: optional run status filter, such as `ok` or `error`.
- `include_payloads`: include per-trace request/response payloads. Default `false`.

## Payload Policy

The endpoint follows `AOH_PAYLOAD_MODE` only when `include_payloads=true`.

Default behavior is summary-first:

```text
include_payloads=false
```

The response includes trace metadata, diagnostics, correlations, timeline metadata, LLM call metadata, and readable derived response text. It does not include raw request/response payloads.

Full local analysis mode:

```text
include_payloads=true
```

The response includes each trace's payloads using the same policy as `/api/traces/{trace_id}/analysis-bundle`:

- `AOH_PAYLOAD_MODE=raw`: raw local payloads
- `AOH_PAYLOAD_MODE=redacted`: redacted payloads

Raw payload mode can expose Authorization headers, cookies, API keys, private prompts, user messages, agent memory, tool inputs/outputs, and file contents. Use it only in trusted local/company-internal environments.

## Response Shape

```json
{
  "subject": {
    "user_hash": "istale"
  },
  "filters": {
    "limit": 10,
    "days": null,
    "agent_id": "hermes",
    "channel": "discord",
    "status": null,
    "include_payloads": false
  },
  "payload_mode": "raw",
  "summary": {
    "trace_count": 2,
    "llm_call_count": 2,
    "total_tokens": 86003,
    "max_latency_ms": 8823,
    "statuses": {
      "ok": 2
    },
    "agents": [
      {
        "agent_id": "hermes",
        "channel": "discord",
        "trace_count": 2
      }
    ]
  },
  "traces": [
    {
      "trace_id": "trace_...",
      "run": {},
      "identity": {},
      "timeline": [],
      "llm_calls": [
        {
          "metadata": {},
          "derived": {
            "assistant_text": "...",
            "reasoning_text": "..."
          },
          "payload_refs": {
            "request_ref": "...",
            "response_ref": null,
            "response_chunks_ref": "..."
          }
        }
      ],
      "correlations": [],
      "diagnostics": {}
    }
  ],
  "diagnostics": {
    "warnings": []
  }
}
```

When `include_payloads=true`, each LLM call also includes:

```json
{
  "payloads": {
    "request": {},
    "response": {},
    "response_chunks": []
  }
}
```

## Usage Flow

```text
/api/subjects/users
-> /api/subjects/users/{user_hash}/analysis-bundle?limit=20&agent_id=hermes&channel=discord
-> /api/traces/{trace_id}/analysis-bundle
```

## Acceptance Criteria

1. Returns a user-centered bundle for recent traces.
2. Supports `limit`, `days`, `agent_id`, `channel`, and `status` filters.
3. Default response does not include payload bodies.
4. `include_payloads=true` includes payloads according to `AOH_PAYLOAD_MODE`.
5. Summary includes trace count, LLM call count, total tokens, max latency, statuses, and agent/channel counts.
6. Missing payload warnings from trace bundles are preserved.
7. Unknown user returns an empty bundle with `trace_count=0`.
