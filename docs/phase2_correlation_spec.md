# Phase 2 Correlation ID Spec

## Purpose

Phase 2 makes Agent Observation Hub useful across Hermes, OpenClaw, LiteLLM, model providers, and channels. Phase 1 can already capture local LLM calls, but many rows still say `unknown` because the gateway does not yet persist external identifiers as first-class correlations.

The goal is to answer questions like:

- Which Hermes or OpenClaw session produced this LLM call?
- Which LiteLLM call id and provider request id map to this local `llm_call_id`?
- Which Discord/Open WebUI/channel conversation delivered or triggered the run?
- Can a user search by session id, LiteLLM call id, channel id, or conversation id and find the trace?

Phase 2 remains observation-only. It must not alter prompts, routing, memory, or agent workflows.

## Scope

In scope:

- Add `external_ids` table.
- Capture inbound metadata headers from Hermes/OpenClaw/Open WebUI/channel callers.
- Capture upstream response headers from LiteLLM and model providers.
- Link every external id to `trace_id`, optionally `run_id` and `llm_call_id`.
- Add API endpoints to query correlations by trace and by external id.
- Add a minimal UI correlation panel.
- Add tests for capture, query, redaction boundaries, and duplicate handling.

Out of scope:

- OpenInference/OTEL export.
- Agent log importer enrichment.
- Tool call capture.
- Automatic failure classification.
- Prompt/model optimization.

## Data Model

Migration:

```sql
CREATE TABLE IF NOT EXISTS external_ids (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id TEXT NOT NULL,
  run_id TEXT,
  llm_call_id TEXT,
  source TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  value_hash TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_external_ids_trace_id ON external_ids(trace_id);
CREATE INDEX IF NOT EXISTS idx_external_ids_run_id ON external_ids(run_id);
CREATE INDEX IF NOT EXISTS idx_external_ids_llm_call_id ON external_ids(llm_call_id);
CREATE INDEX IF NOT EXISTS idx_external_ids_lookup ON external_ids(source, key, value);
CREATE UNIQUE INDEX IF NOT EXISTS idx_external_ids_unique
  ON external_ids(trace_id, COALESCE(run_id, ''), COALESCE(llm_call_id, ''), source, key, value);
```

Recommended sources:

- `gateway`
- `litellm`
- `minimax`
- `openclaw`
- `hermes`
- `openwebui`
- `discord`
- `client`

Recommended keys:

- `agent_id`
- `session_id`
- `conversation_id`
- `channel`
- `channel_id`
- `thread_id`
- `user_id`
- `user_hash`
- `litellm_call_id`
- `provider_trace_id`
- `provider_request_id`
- `minimax_request_id`
- `upstream_session_id`

## Capture Rules

Inbound request headers to persist:

- `X-Agent-Id`
- `X-Session-Id`
- `X-Channel`
- `X-Channel-Id`
- `X-Conversation-Id`
- `X-Thread-Id`
- `X-User-Id`
- `X-User-Hash`
- `X-OpenClaw-Session-Id`
- `X-Hermes-Session-Id`
- `X-OpenWebUI-Conversation-Id`
- `X-Discord-Channel-Id`
- `X-Discord-Thread-Id`
- `X-Discord-User-Id`

Upstream response headers to persist:

- `x-litellm-call-id`
- `x-litellm-model-api-base`
- `llm_provider-trace-id`
- `llm_provider-x-session-id`
- `llm_provider-x-mm-request-id`
- `llm_provider-minimax-request-id`
- `llm_provider-alb_request_id`

Rules:

- Never persist `authorization`, `cookie`, `set-cookie`, or raw API keys into `external_ids`.
- Treat user ids as potentially sensitive. Prefer `X-User-Hash`; if only `X-User-Id` exists, store it as `user_id` only in local mode and plan future hashing before multi-user mode.
- Duplicate ids must be ignored idempotently.
- Unknown metadata should not be dropped if it is explicitly correlation-related, but arbitrary headers should not be copied wholesale.

## API

Add:

- `GET /api/traces/{trace_id}/correlations`
- `GET /api/correlations?source=&key=&value=`

Trace response shape:

```json
{
  "trace_id": "trace_abc",
  "correlations": [
    {
      "source": "litellm",
      "key": "litellm_call_id",
      "value": "156ce4a7-e055-4bba-83a6-c2ea681bcc2a",
      "run_id": "run_abc",
      "llm_call_id": "llm_abc",
      "created_at": "2026-05-30 10:00:00"
    }
  ]
}
```

Lookup response shape:

```json
{
  "matches": [
    {
      "trace_id": "trace_abc",
      "run_id": "run_abc",
      "llm_call_id": "llm_abc",
      "source": "hermes",
      "key": "session_id",
      "value": "session_123"
    }
  ]
}
```

## UI

Add a correlation panel on trace detail:

- Agent/session/channel identity.
- LiteLLM call id.
- Provider request ids.
- Channel/conversation ids.
- Copyable values for search/debugging.

Keep the panel compact. The UI should help operators answer "where did this come from?" without becoming a full observability dashboard.

## Testing

Required tests:

- Migration is idempotent.
- Request headers are captured into `external_ids`.
- LiteLLM/provider response headers are captured into `external_ids`.
- Duplicate correlations do not create duplicate rows.
- `/api/traces/{trace_id}/correlations` returns trace-scoped ids.
- `/api/correlations` can find traces by session id or LiteLLM call id.
- UI trace detail shows the correlation panel.
- Redaction/security test proves `authorization`, `cookie`, and API-key-like headers are not persisted as external ids.

## Acceptance

Run a request with:

```text
X-Agent-Id: hermes
X-Session-Id: hermes-session-123
X-Channel: desktop
X-Conversation-Id: conv-456
```

Expected:

- `llm_calls.agent_id=hermes`
- `llm_calls.session_id=hermes-session-123`
- `external_ids` contains Hermes/session/channel/conversation ids.
- `external_ids` contains LiteLLM call id from response headers.
- Trace detail UI shows a Correlations panel.
- Search by `source=hermes&key=session_id&value=hermes-session-123` returns the trace.

## Implementation Effort

Estimated effort: 1 to 1.5 focused development days.

Breakdown:

- Migration and repository methods: 1.5-2 hours.
- Header capture mapping and tests: 2-3 hours.
- API endpoints: 1-2 hours.
- UI panel: 1-2 hours.
- Security/redaction tests: 1 hour.
- Manual Hermes/OpenClaw verification: 1-2 hours.

Main risk:

- Header names vary by client/provider. Mitigation is to start with a strict allowlist and add mappings as observed in real traces.
