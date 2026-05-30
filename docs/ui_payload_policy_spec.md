# UI Payload Policy Spec

## Purpose

Agent Observation Hub is observation-first. For private company deployments, operators often need to see the exact request and response payloads sent through the agent system. If the UI redacts payloads too early, users cannot judge whether the redacted data was actually sensitive, whether redaction hid an important context assembly bug, or whether the agent/model received the right information.

This spec defines a configurable payload policy so the UI and local raw API can operate in raw-first mode for private/local observation while preserving redaction support for safer modes and future exporters.

## Problem

The current UI labels request/response payloads as:

```text
Redacted Request
Redacted Response JSON
```

This is safe, but it can confuse users during agent debugging:

- They may not know what was hidden.
- They cannot decide whether the hidden content was worth redacting.
- They cannot fully inspect prompt/context assembly.
- They may misdiagnose agent behavior because the displayed payload is not exactly what the model saw.

Agent systems change quickly, and observation quality is more important than premature masking in this project stage.

## Design Goal

Support two payload modes:

```text
AOH_PAYLOAD_MODE=raw
AOH_PAYLOAD_MODE=redacted
```

Recommended local/private default:

```text
AOH_PAYLOAD_MODE=raw
```

Recommended shared/demo/cloud/exporter default:

```text
AOH_PAYLOAD_MODE=redacted
```

## Behavior

### Raw Mode

When:

```text
AOH_PAYLOAD_MODE=raw
```

UI behavior:

- LLM call detail reads payloads directly from raw archive.
- Trace embedded readable response uses raw payloads.
- UI section titles say:
  - `Raw Request JSON`
  - `Raw Response JSON`
  - `Raw Stream Chunks`
- UI should show a clear label:
  - `Payload mode: raw`

API behavior:

- `GET /api/raw/{payload_ref}` returns raw payloads by default.
- `raw=true` is not required in raw mode.
- Path traversal protection still applies.

This mode is intended for private/local/company-internal debugging and for local LLM agents that need complete payloads to analyze agent and model behavior.

### Redacted Mode

When:

```text
AOH_PAYLOAD_MODE=redacted
```

UI behavior:

- LLM call detail reads raw archive and applies `redact()`.
- Trace embedded readable response uses redacted payloads.
- UI section titles say:
  - `Redacted Request JSON`
  - `Redacted Response JSON`
  - `Redacted Stream Chunks`
- UI should show a clear label:
  - `Payload mode: redacted`

API behavior:

- `GET /api/raw/{payload_ref}` returns redacted payloads by default.
- The raw archive remains stored locally, but this endpoint does not expose it in redacted mode.

This mode is intended for safer sharing, demos, and future multi-user/cloud scenarios.

## API Boundary

This spec changes both UI rendering and the local raw API response policy.

The raw API should keep its existing path safety model while changing response redaction behavior to follow the payload mode:

```text
GET /api/raw/{payload_ref}
```

Default:

- follows `AOH_PAYLOAD_MODE`.

Raw access:

- `AOH_PAYLOAD_MODE=raw` returns raw payloads by default.
- `AOH_PAYLOAD_MODE=redacted` returns redacted payloads.
- `ALLOW_RAW_VIEW` is deprecated for this raw-first local observation workflow and should not be used as the primary policy switch.

Reason:

- UI and local helper agents are both observation clients.
- Local LLM agents need complete request/response payloads to analyze prompt assembly, context, model behavior, and agent failures.
- Shared, demo, cloud, and exporter use cases should set `AOH_PAYLOAD_MODE=redacted`.

## Raw Archive

Raw archive behavior does not change.

Raw payloads remain stored locally under:

```text
data/raw/YYYY-MM-DD/trace_<trace_id>/
```

The payload mode controls how those local raw files are rendered through UI and exposed through `/api/raw/{payload_ref}`.

## Configuration

Add setting:

```text
AOH_PAYLOAD_MODE=raw
```

Allowed values:

- `raw`
- `redacted`

Invalid values should fall back to `redacted` or raise a clear startup/config error. Recommendation: fall back to `redacted` and log a warning.

Update `.env.example`:

```text
# raw is recommended for private/local observation; redacted is safer for shared demos.
AOH_PAYLOAD_MODE=raw
```

## UI Labels

LLM call detail page:

```text
Payload mode: raw
Raw Request JSON
Raw Response JSON
Raw Stream Chunks
```

or:

```text
Payload mode: redacted
Redacted Request JSON
Redacted Response JSON
Redacted Stream Chunks
```

Trace page:

- Keep `Readable Response`.
- If payload-derived text is raw, show `Payload mode: raw`.
- If payload-derived text is redacted, show `Payload mode: redacted`.

## Security Notes

Raw mode may expose:

- Authorization headers
- API keys
- Cookies
- passwords/secrets/tokens
- private prompts
- user messages
- agent memory
- tool outputs
- file contents

Raw mode should be used only in trusted private/local deployments.

Redaction functionality must remain available.

Future exporters should default to redacted unless explicitly configured otherwise.

## Acceptance Tests

### Test 1: Raw UI Mode Shows Unredacted Payload

Given:

```text
AOH_PAYLOAD_MODE=raw
```

And request payload includes:

```text
Authorization: Bearer secret-token
content: 天命（The Destiny）
```

Expected:

- LLM detail page shows `Raw Request JSON`.
- LLM detail page shows `Bearer secret-token`.
- LLM detail page shows `天命（The Destiny）`.
- LLM detail page does not label the section as redacted.
- `/api/raw/{payload_ref}` shows `Bearer secret-token`.

### Test 2: Redacted Mode Hides Secret

Given:

```text
AOH_PAYLOAD_MODE=redacted
```

And request payload includes:

```text
Authorization: Bearer secret-token
```

Expected:

- LLM detail page shows `Redacted Request JSON`.
- LLM detail page does not show `secret-token`.
- LLM detail page shows `[REDACTED]`.
- `/api/raw/{payload_ref}` does not show `secret-token`.

### Test 3: API Follows Payload Mode

Given:

```text
AOH_PAYLOAD_MODE=raw
```

Expected:

- UI may show raw payload.
- `/api/raw/{payload_ref}` returns raw payload.
- `/api/raw/{payload_ref}?raw=true` also returns raw payload.

Given:

```text
AOH_PAYLOAD_MODE=redacted
```

Expected:

- UI shows redacted payload.
- `/api/raw/{payload_ref}` returns redacted payload.

### Test 4: Invalid Mode Is Safe

Given:

```text
AOH_PAYLOAD_MODE=invalid
```

Expected:

- UI falls back to redacted mode.
- Payload mode label shows `redacted`.

## Implementation Plan

1. Add `payload_mode` to settings.
2. Add helper:

```text
load_payload(payload_ref) -> raw or redacted payload based on settings
```

3. Update `llm_call_page`.
4. Update `trace_page` embedded response rendering.
5. Update `/api/raw/{payload_ref}` to follow `AOH_PAYLOAD_MODE`.
6. Update UI templates and labels.
7. Update `.env.example` and README.
8. Add tests for raw mode, redacted mode, API payload policy, and invalid mode fallback.

## Recommendation

Proceed with this change before deeper evaluation/exporter work.

For the current private company observation workflow, use:

```text
AOH_PAYLOAD_MODE=raw
```

Keep redaction as a supported mode for future sharing, multi-user access, and cloud/exporter use cases. Raw mode should be treated as a trusted local/company-internal analysis mode and may expose secrets to any client that can reach the hub API.
