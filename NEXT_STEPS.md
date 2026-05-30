# NEXT_STEPS

## Done

- MVP Gateway implemented as OpenAI-compatible proxy.
- Raw payloads are stored under `data/raw/YYYY-MM-DD/trace_<trace_id>/`.
- SQLite stores trace/run/LLM metadata and payload refs.
- Redaction is enabled by default for raw API and UI.
- Cookie and `set-cookie` headers are redacted.
- Non-stream and stream `/v1/chat/completions` paths are implemented.
- Completed LLM calls finalize `trace_runs.status` and `trace_runs.ended_at`.
- Upstream HTTP 500 and transport errors have regression coverage.
- Streaming usage chunks are normalized into `llm_calls` when usage is visible in captured SSE data.
- Raw archive traversal and disabled raw-view behavior have regression coverage.
- `/v1/responses` pass-through exists.
- Minimal UI exists for recent runs, trace timeline, and LLM call detail.
- OpenClaw/Hermes importer skeletons exist.
- Exporter skeletons exist for OTEL, Opik, and Langfuse.
- Python 3.12 test environment `.venv312` was used for verification.
- Hermes has produced real MiniMax traces through the Hub.

## Known Issues

- Streaming parser remains best-effort. It now scans coalesced `data:` lines for usage, but it is not yet a full SSE event-buffer parser.
- Importers are skeletons and do not yet parse native OpenClaw/Hermes sessions.
- No correlation table exists yet for LiteLLM/Hermes/OpenClaw/Discord/Open WebUI IDs.
- No OpenInference/OpenTelemetry preview API exists yet.
- Canonical docs now use port `43180`; any Hermes/OpenClaw instance still pointing to `8080` must be migrated or run the Hub with `PORT=8080`.

## Security Risks

- Raw request files contain full system prompts, context, tool outputs, and headers.
- Importer unknown logs can be stored in SQLite `payload_json`.
- `ALLOW_RAW_VIEW=true` exposes raw local payloads through API.
- Exporter implementations must remain disabled by default and must not send raw payloads to cloud by default.

## Recommended Next Phase

Proceed to Phase 2 Correlation ID only after one manual Hermes validation on canonical port `43180`.

Recommended Phase 2 scope:

1. Add `external_ids` table.
2. Persist LiteLLM/upstream call IDs from response headers and payloads.
3. Persist Hermes/OpenClaw/Open WebUI/Discord identifiers from headers and importers.
4. Add `/api/traces/{trace_id}/correlations`.
5. Add a correlation panel to the trace UI.

## Commands to Run

```sh
.venv312/bin/python -m pytest -q
.venv312/bin/python -m compileall -q app
curl -sS http://127.0.0.1:8080/healthz
curl -sS http://127.0.0.1:8080/api/traces
curl -sS http://127.0.0.1:43180/healthz
curl -sS http://127.0.0.1:43180/api/traces
```

## Manual Verification Steps

1. Send one Hermes non-stream request through `http://127.0.0.1:43180/v1`.
2. Send one Hermes streaming request through `http://127.0.0.1:43180/v1`.
3. Open `http://127.0.0.1:43180`.
4. Confirm latest trace appears.
5. Open trace detail and LLM call detail.
6. Confirm request/response/chunks refs exist.
7. Confirm UI displays redacted payloads.
8. Inspect `data/raw/...` locally for the full raw archive.
