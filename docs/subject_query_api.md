# Subject Query API

## Purpose

Subject query APIs help local LLM agents and operators choose which traces to analyze before calling the per-trace analysis bundle API.

The intended workflow is:

1. List observed users.
2. Pick a user and optionally an agent/channel.
3. Fetch that user's recent traces.
4. Call `/api/traces/{trace_id}/analysis-bundle` for deeper analysis.

## List Observed Users

```text
GET /api/subjects/users
```

Response:

```json
{
  "users": [
    {
      "user_hash": "istale",
      "trace_count": 2,
      "agent_count": 1,
      "channels": ["discord"],
      "first_seen": "2026-05-30T18:15:01Z",
      "last_seen": "2026-05-30T18:17:13Z"
    }
  ]
}
```

`user_hash` is the analysis subject identifier. Raw user IDs should not be required for the first private/local workflow.

## List User Traces

```text
GET /api/subjects/users/{user_hash}/traces
```

Query parameters:

- `limit`: maximum traces to return. Default `50`.
- `days`: only include traces started within the last N days.
- `agent_id`: optional agent filter, such as `hermes`.
- `channel`: optional channel filter, such as `discord`.
- `status`: optional run status filter, such as `ok` or `error`.

Examples:

```sh
curl "http://127.0.0.1:43180/api/subjects/users/istale/traces?limit=20"
curl "http://127.0.0.1:43180/api/subjects/users/istale/traces?days=7&agent_id=hermes&channel=discord"
```

Response:

```json
{
  "user_hash": "istale",
  "filters": {
    "limit": 20,
    "days": null,
    "agent_id": null,
    "channel": null,
    "status": null
  },
  "traces": [
    {
      "trace_id": "trace_...",
      "run_id": "run_...",
      "tenant_id": "local",
      "user_hash": "istale",
      "agent_id": "hermes",
      "channel": "discord",
      "status": "ok",
      "started_at": "2026-05-30T18:17:13Z",
      "ended_at": "2026-05-30T18:17:22Z",
      "identity_source": "ingress_route",
      "llm_call_count": 1,
      "total_tokens": 85949,
      "max_latency_ms": 8823
    }
  ]
}
```

## List User Agents

```text
GET /api/subjects/users/{user_hash}/agents
```

Response:

```json
{
  "user_hash": "istale",
  "agents": [
    {
      "agent_id": "hermes",
      "channel": "discord",
      "trace_count": 2,
      "last_seen": "2026-05-30T18:17:13Z"
    }
  ]
}
```

## Notes

These endpoints summarize metadata only. They do not return raw request or response payloads. Use `/api/traces/{trace_id}/analysis-bundle` after selecting a trace.
