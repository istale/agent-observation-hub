# Agent Observation Hub Audit Report

Date: 2026-05-30

## Executive Summary

The current repository implements a working MVP of `agent-observation-hub` as an OpenAI-compatible observation proxy between Hermes/OpenClaw and LiteLLM. The core proxy path, raw archive, SQLite metadata storage, redaction defaults, minimal UI, and tests are present.

Current validated local topology:

```text
Hermes -> http://127.0.0.1:8080/v1
Hub    -> http://127.0.0.1:4000
LiteLLM -> MiniMax
```

The handoff target topology uses port `43180` for the Hub. The running local integration currently uses `8080`; changing that should be a deliberate migration step.

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
| `llm_calls` updates status/latency/http status/refs | Partial | Works for normal completion and completed stream; upstream 500 body preservation needs stronger tests |
| Usage tokens saved | Partial | Non-stream usage saved; streaming usage chunks are captured but not normalized into token columns |
| Redaction covers core secrets | Partial | Authorization, Bearer, API key pattern, email, password/token/secret/key fields, SSH private key covered; cookies are not explicitly redacted |
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

1. **Cookie redaction is missing.** `authorization` is covered, but `cookie` / `set-cookie` are not in `SENSITIVE_FIELD_RE`.
2. **Run status remains `running`.** `llm_calls.status` is updated, but `trace_runs.status` is not ended/updated after response completion.
3. **Streaming usage is not normalized.** MiniMax/LiteLLM can emit usage in a final stream chunk; it is archived but not extracted into `llm_calls`.
4. **Client disconnect semantics are weak.** The stream iterator catches exceptions and writes `llm_error`, but disconnect-specific handling and cancellation tests are missing.
5. **Upstream 500 behavior needs stronger evidence.** Current code writes response body and sets status based on HTTP code for non-stream, but tests do not assert `llm_error` for an HTTP 500 response.
6. **Importer raw exposure is underdesigned.** Importers store unknown logs in `payload_json`; UI/API treatment of imported unknown logs is not yet governed by sensitivity rules.

## Most Dangerous Data Leakage Points

- Full request archives contain system prompts, tool outputs, session context, and authorization headers before redaction.
- `/api/raw/{payload_ref}?raw=true` can expose raw local payloads if `ALLOW_RAW_VIEW=true`.
- Cookie headers are not explicitly masked.
- Importer `payload_json` can put unknown log content directly into SQLite instead of raw archive.
- Cloud exporters are no-op today, but future implementations must default to disabled and redacted-only unless explicitly configured.

## Most Fragile Streaming Logic

- The gateway writes chunks exactly as received from `httpx.aiter_bytes()`. Chunk boundaries may not align with SSE event boundaries.
- `chunk_record()` tries to parse a chunk as one complete `data:` event. If providers split or coalesce SSE events, JSON parsing may be partial.
- Final stream usage chunks are archived but not normalized into `llm_calls.input_tokens/output_tokens/total_tokens`.
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

