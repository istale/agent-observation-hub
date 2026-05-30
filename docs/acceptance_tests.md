# Acceptance Tests

These scenarios define minimum acceptance for the next stabilization phase.

## Test 1: Non-Stream Chat Completion

Steps:

1. Start mock upstream or LiteLLM.
2. Send a non-stream request to the Gateway:

   ```sh
   curl -i http://127.0.0.1:8080/v1/chat/completions \
     -H 'content-type: application/json' \
     -H 'X-Trace-Id: trace_accept_non_stream' \
     -H 'X-Run-Id: run_accept_non_stream' \
     -d '{"model":"MiniMax-M2.7","messages":[{"role":"user","content":"hello"}],"max_tokens":20}'
   ```

3. Check response body and status.
4. Check SQLite `llm_calls`.
5. Check raw archive files.
6. Check UI trace page.

Expected:

- HTTP response succeeds.
- Response headers include `X-Trace-Id`, `X-Run-Id`, `X-LLM-Call-Id`.
- `llm_calls.status='ok'`.
- `request_ref` exists.
- `response_ref` exists.
- `latency_ms > 0`.
- `http_status=200`.

## Test 2: Streaming Chat Completion

Steps:

1. Send a streaming request:

   ```sh
   curl -N -i http://127.0.0.1:8080/v1/chat/completions \
     -H 'content-type: application/json' \
     -H 'X-Trace-Id: trace_accept_stream' \
     -H 'X-Run-Id: run_accept_stream' \
     -d '{"model":"MiniMax-M2.7","stream":true,"messages":[{"role":"user","content":"hello"}],"max_tokens":20}'
   ```

2. Confirm client receives SSE chunks.
3. Confirm Gateway writes chunks JSONL.
4. Confirm DB updates after stream ends.

Expected:

- `response_chunks_ref` exists.
- Chunks JSONL has at least one line.
- `llm_calls.status='ok'`.
- `latency_ms > 0`.
- `http_status=200`.

## Test 3: Upstream Error

Steps:

1. Configure mock upstream to return HTTP 500.
2. Send a non-stream request through Gateway.
3. Inspect response, DB, raw archive, and trace events.

Expected:

- Gateway returns upstream error status.
- Error payload is archived.
- `llm_calls.status='error'`.
- `llm_calls.http_status=500`.
- `error_message` is populated or response body is referenced.
- `trace_events` contains `llm_error`.

## Test 4: Redaction

Steps:

1. Send request containing:
   - `Authorization: Bearer secret-token`
   - email address
   - `password`
   - `api_key`
   - cookie header
2. Fetch raw API without `raw=true`.
3. Fetch raw API with `raw=true` while `ALLOW_RAW_VIEW=false`.
4. Open UI LLM call detail.

Expected:

- Default API response is redacted.
- `ALLOW_RAW_VIEW=false` prevents raw output even with `raw=true`.
- Authorization, Bearer token, email, password/token/secret/key fields are redacted.
- Cookie is redacted after the stabilization fix.
- UI never displays raw secrets by default.

## Test 5: Importer

Steps:

1. Prepare sample OpenClaw and Hermes logs:

   ```sh
   printf '{"event_type":"test_event","message":"hello"}\nplain fallback\n' > /tmp/aoh-importer-sample.log
   ```

2. Run importer:

   ```sh
   AOH_DATABASE_PATH=/tmp/aoh-importer.sqlite3 \
   AOH_DATA_DIR=/tmp/aoh-importer-data \
   python -m app.importers.hermes_importer --path /tmp/aoh-importer-sample.log
   ```

3. Query `trace_events`.

Expected:

- Parsed JSON log creates an event.
- Plain log creates `external_log`.
- `source='hermes'` or `source='openclaw'`.
- Unparseable log lines do not crash the importer.

## Test 6: Correlation

Steps:

1. Send request with:
   - `X-Agent-Id`
   - `X-Session-Id`
   - `X-Channel`
   - `X-Channel-Id`
   - `X-Conversation-Id`
2. Query trace API and UI.

Expected:

- Metadata appears in `trace_runs` and `llm_calls`.
- Phase 2 adds `/api/traces/{trace_id}/correlations`.
- UI trace detail shows a correlation panel.

