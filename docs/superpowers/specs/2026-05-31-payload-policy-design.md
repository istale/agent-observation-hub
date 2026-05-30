# Payload Policy Design

## Purpose

Agent Observation Hub is used as a private/local observation system. Operators and local LLM helper agents need to inspect the exact request, response, and streaming payloads that passed through the gateway. Redacting too early makes it harder to diagnose prompt assembly, missing context, model behavior, and agent failures.

## Decision

Use one shared payload policy for both UI rendering and the local raw API:

```text
AOH_PAYLOAD_MODE=raw
AOH_PAYLOAD_MODE=redacted
```

`raw` is the recommended mode for trusted local or private company deployments. `redacted` is the recommended mode for demos, shared environments, cloud access, and future exporters.

## Raw Mode

When `AOH_PAYLOAD_MODE=raw`:

- UI pages show raw request, response, and stream chunk payloads.
- `/api/raw/{payload_ref}` returns raw payloads by default.
- `raw=true` is not required.
- Local LLM agents can call the API directly to analyze complete observation data.
- Path traversal protection remains mandatory.

The UI should clearly label this state with `Payload mode: raw`.

## Redacted Mode

When `AOH_PAYLOAD_MODE=redacted`:

- UI pages show redacted request, response, and stream chunk payloads.
- `/api/raw/{payload_ref}` returns redacted payloads.
- Raw archives remain stored locally but are not exposed by the API.

The UI should clearly label this state with `Payload mode: redacted`.

## Invalid Configuration

Invalid `AOH_PAYLOAD_MODE` values fall back to `redacted`. This keeps accidental misconfiguration from exposing raw payloads.

## Security Notice

Raw mode can expose Authorization headers, cookies, API keys, passwords, private prompts, user messages, agent memory, tool inputs/outputs, file contents, and other sensitive data. It should only be used when every client that can reach Agent Observation Hub is trusted. This is acceptable for the current private local-LLM analysis workflow, but should be changed to `redacted` before sharing the hub, opening it to a network, or enabling cloud/exporter integrations.

## Testing

Acceptance tests should cover:

- Raw mode UI shows unredacted content and raw labels.
- Raw mode `/api/raw/{payload_ref}` returns unredacted content.
- Redacted mode UI hides secrets and shows redacted labels.
- Redacted mode `/api/raw/{payload_ref}` hides secrets.
- Invalid mode falls back to redacted.
- Path traversal remains blocked in all modes.
