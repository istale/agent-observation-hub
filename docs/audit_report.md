# Agent Observation Hub Audit Report

Date: 2026-05-30
Updated after Phase 1 stabilization implementation.

## Executive Summary

The current repository implements a working MVP of `agent-observation-hub` as an OpenAI-compatible observation proxy between Hermes/OpenClaw and LiteLLM. The core proxy path, raw archive, SQLite metadata storage, redaction defaults, minimal UI, and tests are present.

Original validated local topology:

```text
Hermes -> http://127.0.0.1:8080/v1
Hub    -> http://127.0.0.1:4000
LiteLLM -> MiniMax
```

Phase 1 makes `43180` the canonical documented Hub port. `8080` remains a temporary compatibility override for already-running local Hermes setups.

## Checklist

| Item | Status | Evidence |
|---|---:|---|
| Project can start | Pass | `uvicorn app.main:app` previously started; live `GET /healthz` returned `{"status":"ok"}` |
| SQLite migration repeatable | Pass | `init_db(); init_db()` on `/private/tmp/aoh-audit.sqlite3` returned `migration-repeat-ok` |
| `/healthz` works | Pass | `curl http://127.0.0.1:8080/healthz` returned `{"status":"ok"}` |
| Non-stream proxy works | Pass | `tests/test_openai_proxy_non_stream.py`; real MiniMax smoke trace `trace_final_background_minimax` status `ok` |
| Stream proxy works | Pass | `tests/test_openai_proxy_stream.py`; Hermes traces show `response_chunks_ref` and chunk JSONL |
| Raw archive writes files | Pass | `data/raw/YYYY-MM-DD/trace_<trace_id>/...` contains request/response/chunks files |
| Response trace headers present | Pass | Covered by non-stream proxy test for `X-Trace-Id`, `X-Run-Id`, `X-LLM-Call-Id` |
| `llm_calls` updates status/latency/http status/refs | Pass | Non-stream, stream, HTTP 500, and transport-error tests cover status/refs |
| Usage tokens saved | Pass | Non-stream usage saved; streaming final usage chunks are normalized when visible in captured SSE data |
| Redaction covers core secrets | Pass | Authorization, Bearer, API key pattern, email, password/token/secret/key fields, SSH private key, cookie, and set-cookie are covered |
| UI shows recent runs/timeline/detail/redacted payload | Pass | Templates exist and `tests/test_ui.py` covers index render; LLM detail renders redacted request/response |
| Importer skeleton executable | Pass | `app.importers.hermes_importer --path /private/tmp/aoh-importer-sample.log` returned `importer-ok` |
| Tests runnable | Pass | `.venv312/bin/python -m pytest -q` returned `7 passed` |

## Current Strengths

- Raw payloads are stored on disk, not directly in SQLite.
- SQLite contains metadata and payload refs.
- API raw endpoint is redacted by default and only returns raw when `ALLOW_RAW_VIEW=true` and `raw=true`.
- Raw archive path resolution blocks `payload_ref` path traversal outside the archive root.
- Streaming chunks are forwarded and appended to JSONL.
- Hermes integration has already generated real traces with `MiniMax-M2.7`.

## Highest-Risk Gaps

1. **Client disconnect semantics are weak.** The stream iterator catches exceptions and writes `llm_error`, but disconnect-specific handling and cancellation tests are missing.
2. **Streaming parsing is still best-effort.** Usage extraction now scans coalesced `data:` lines, but this is not a full SSE event-buffer parser.
3. **Importer raw exposure is underdesigned.** Importers store unknown logs in `payload_json`; UI/API treatment of imported unknown logs is not yet governed by sensitivity rules.
4. **Correlation is missing.** There is still no `external_ids` table for LiteLLM, Hermes, OpenClaw, Open WebUI, or Discord IDs.

## Most Dangerous Data Leakage Points

- Full request archives contain system prompts, tool outputs, session context, and authorization headers before redaction.
- `/api/raw/{payload_ref}?raw=true` can expose raw local payloads if `ALLOW_RAW_VIEW=true`.
- Importer `payload_json` can put unknown log content directly into SQLite instead of raw archive.
- Cloud exporters are no-op today, but future implementations must default to disabled and redacted-only unless explicitly configured.

## Most Fragile Streaming Logic

- The gateway writes chunks exactly as received from `httpx.aiter_bytes()`. Chunk boundaries may not align with SSE event boundaries.
- `chunk_record()` tries to parse a chunk as one complete `data:` event. If providers split or coalesce SSE events, JSON parsing may be partial.
- Final stream usage chunks are normalized when usage appears as parseable `data:` JSON in captured chunks.
- Disconnect/cancellation handling is not covered by tests.

## Schema Gaps

- No `external_ids` table for LiteLLM call IDs, Hermes/OpenClaw session IDs, Discord/Open WebUI IDs, or backend trace IDs.
- No failure labeling table.
- No eval/replay tables.
- `trace_events.payload_json` allows payload content in SQLite, which conflicts with a strict "raw payload only in files" policy for imported logs.
- No normalized tool call parsing/joining despite `tool_calls` table existing.
- No OpenInference/OpenTelemetry span mapping tables or preview API.

## Verification Commands Run

```sh
.venv312/bin/python -m pytest -q
# 7 passed in 0.08s

.venv312/bin/python -m compileall -q app
# exit 0

AOH_DATABASE_PATH=/private/tmp/aoh-audit.sqlite3 .venv312/bin/python - <<'PY'
from app.storage.db import init_db
init_db()
init_db()
print('migration-repeat-ok')
PY
# migration-repeat-ok
```
