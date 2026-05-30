# NEXT_STEPS

## Done

- MVP Gateway implemented as OpenAI-compatible proxy.
- Raw payloads are stored under `data/raw/YYYY-MM-DD/trace_<trace_id>/`.
- SQLite stores trace/run/LLM metadata and payload refs.
- Redaction is enabled by default for raw API and UI.
- Non-stream and stream `/v1/chat/completions` paths are implemented.
- `/v1/responses` pass-through exists.
- Minimal UI exists for recent runs, trace timeline, and LLM call detail.
- OpenClaw/Hermes importer skeletons exist.
- Exporter skeletons exist for OTEL, Opik, and Langfuse.
- Python 3.12 test environment `.venv312` was used for verification.
- Hermes has produced real MiniMax traces through the Hub.

## Known Issues

- `trace_runs.status` remains `running` after LLM completion.
- Streaming usage chunks are archived but not normalized into token columns.
- Streaming parser assumes `httpx` chunk boundaries align closely enough with SSE events.
- Upstream HTTP 500 behavior needs stronger automated tests.
- Importers are skeletons and do not yet parse native OpenClaw/Hermes sessions.
- No correlation table exists yet for LiteLLM/Hermes/OpenClaw/Discord/Open WebUI IDs.
- No OpenInference/OpenTelemetry preview API exists yet.

## Security Risks

- Raw request files contain full system prompts, context, tool outputs, and headers.
- Cookie and `set-cookie` redaction are not explicitly implemented yet.
- Importer unknown logs can be stored in SQLite `payload_json`.
- `ALLOW_RAW_VIEW=true` exposes raw local payloads through API.
- Exporter implementations must remain disabled by default and must not send raw payloads to cloud by default.

## Recommended Next Phase

Run Phase 1 Stabilization before adding correlation or evaluation:

1. Add cookie/set-cookie redaction.
2. Add tests for path traversal and raw-view denial with `ALLOW_RAW_VIEW=false`.
3. Update `trace_runs` to completed/error after the last LLM call.
4. Normalize usage from final streaming chunks.
5. Add upstream HTTP 500 tests that assert archived error payload and `llm_error`.
6. Add client-disconnect/cancellation tests for streaming.
7. Decide whether canonical Hub port is `8080` or `43180`, then update scripts, README, and Hermes/OpenClaw instructions consistently.

## Commands to Run

```sh
.venv312/bin/python -m pytest -q
.venv312/bin/python -m compileall -q app
curl -sS http://127.0.0.1:8080/healthz
curl -sS http://127.0.0.1:8080/api/traces
```

## Manual Verification Steps

1. Send one Hermes non-stream request through `http://127.0.0.1:8080/v1`.
2. Send one Hermes streaming request through `http://127.0.0.1:8080/v1`.
3. Open `http://127.0.0.1:8080`.
4. Confirm latest trace appears.
5. Open trace detail and LLM call detail.
6. Confirm request/response/chunks refs exist.
7. Confirm UI displays redacted payloads.
8. Inspect `data/raw/...` locally for the full raw archive.

