# UI Payload Policy Spec

## Purpose

Agent Observation Hub is observation-first. For private company deployments, operators often need to see the exact request and response payloads sent through the agent system. If the UI redacts payloads too early, users cannot judge whether the redacted data was actually sensitive, whether redaction hid an important context assembly bug, or whether the agent/model received the right information.

This spec defines a configurable UI payload policy so the UI can operate in raw-first mode for private/local observation while preserving redaction support for safer modes and future exporters.

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

Support two UI payload modes:

```text
AOH_UI_PAYLOAD_MODE=raw
AOH_UI_PAYLOAD_MODE=redacted
```

Recommended local/private default:

```text
AOH_UI_PAYLOAD_MODE=raw
```

Recommended shared/demo/cloud/exporter default:

```text
AOH_UI_PAYLOAD_MODE=redacted
```

## Behavior

### Raw Mode

When:

```text
AOH_UI_PAYLOAD_MODE=raw
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

This mode is intended for private/local/company-internal debugging.

### Redacted Mode

When:

```text
AOH_UI_PAYLOAD_MODE=redacted
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

This mode is intended for safer sharing, demos, and future multi-user/cloud scenarios.

## API Boundary

This spec changes UI behavior only.

The raw API should keep its existing safety model:

```text
GET /api/raw/{payload_ref}
```

Default:

- returns redacted payload.

Raw access:

- only when `ALLOW_RAW_VIEW=true`
- and query includes `raw=true`

Reason:

- UI is a local operator console.
- API may be consumed by scripts, exporters, or future remote clients.
- Keeping the API conservative avoids accidental raw leakage.

## Raw Archive

Raw archive behavior does not change.

Raw payloads remain stored locally under:

```text
data/raw/YYYY-MM-DD/trace_<trace_id>/
```

The UI mode only controls how those local raw files are rendered.

## Configuration

Add setting:

```text
AOH_UI_PAYLOAD_MODE=raw
```

Allowed values:

- `raw`
- `redacted`

Invalid values should fall back to `redacted` or raise a clear startup/config error. Recommendation: fall back to `redacted` and log a warning.

Update `.env.example`:

```text
# raw is recommended for private/local observation; redacted is safer for shared demos.
AOH_UI_PAYLOAD_MODE=raw
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
AOH_UI_PAYLOAD_MODE=raw
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

### Test 2: Redacted UI Mode Hides Secret

Given:

```text
AOH_UI_PAYLOAD_MODE=redacted
```

And request payload includes:

```text
Authorization: Bearer secret-token
```

Expected:

- LLM detail page shows `Redacted Request JSON`.
- LLM detail page does not show `secret-token`.
- LLM detail page shows `[REDACTED]`.

### Test 3: API Raw Policy Unchanged

Given:

```text
AOH_UI_PAYLOAD_MODE=raw
ALLOW_RAW_VIEW=false
```

Expected:

- UI may show raw payload.
- `/api/raw/{payload_ref}?raw=true` still does not return raw.

### Test 4: Invalid Mode Is Safe

Given:

```text
AOH_UI_PAYLOAD_MODE=invalid
```

Expected:

- UI falls back to redacted mode.
- Payload mode label shows `redacted`.

## Implementation Plan

1. Add `ui_payload_mode` to settings.
2. Add helper:

```text
load_ui_payload(payload_ref) -> raw or redacted payload based on settings
```

3. Update `llm_call_page`.
4. Update `trace_page` embedded response rendering.
5. Update UI templates and labels.
6. Update `.env.example` and README.
7. Add tests for raw mode, redacted mode, unchanged API raw policy, and invalid mode fallback.

## Recommendation

Proceed with this change before deeper evaluation/exporter work.

For the current private company observation workflow, use:

```text
AOH_UI_PAYLOAD_MODE=raw
ALLOW_RAW_VIEW=true
```

Keep redaction as a supported mode for future sharing, multi-user access, and cloud/exporter use cases.
