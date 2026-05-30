# Observation Hub Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current Agent Observation Gateway reliable enough for ongoing Hermes/OpenClaw observation before adding correlation, OpenInference export, tool capture, or evaluation.

**Architecture:** Keep the Hub in front of LiteLLM. Preserve local raw archive as the source of raw payload truth, and keep SQLite limited to metadata, refs, status, usage, and indexes. Add stabilization behavior through focused repository methods, proxy tests, and security tests.

**Tech Stack:** Python 3.12, FastAPI, httpx, SQLite, pytest, respx, server-rendered Jinja UI.

---

## File Structure

- Modify `app/trace/redaction.py`: add cookie redaction and stronger field matching.
- Modify `app/storage/repositories.py`: add run finalization and optional event queries needed by tests.
- Modify `app/gateway/openai_proxy.py`: finalize runs, normalize stream usage, persist upstream error bodies, and improve stream cancellation state.
- Modify `app/gateway/streaming_capture.py`: parse SSE records more robustly and extract final usage chunks.
- Modify `app/api/raw.py`: keep raw-view denial strict and test path traversal.
- Modify `README.md`, `.env.example`, `scripts/dev.sh` only after the canonical gateway port decision.
- Add tests in `tests/test_security_redaction.py`, `tests/test_openai_proxy_errors.py`, and `tests/test_openai_proxy_stream.py`.

## Task 1: Security Redaction Hardening

**Files:**
- Modify: `app/trace/redaction.py`
- Test: `tests/test_security_redaction.py`

- [ ] **Step 1: Write failing tests for cookie and raw-view denial**

```python
from app.trace.redaction import redact


def test_redaction_masks_cookie_headers():
    payload = {
        "headers": {
            "cookie": "sessionid=secret",
            "set-cookie": "refresh=secret; HttpOnly",
        }
    }

    rendered = str(redact(payload))

    assert "sessionid=secret" not in rendered
    assert "refresh=secret" not in rendered
    assert "[REDACTED]" in rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```sh
.venv312/bin/python -m pytest tests/test_security_redaction.py::test_redaction_masks_cookie_headers -q
```

Expected: FAIL because cookie fields are not currently redacted.

- [ ] **Step 3: Implement minimal redaction update**

Change `SENSITIVE_FIELD_RE` in `app/trace/redaction.py` to include cookie headers:

```python
SENSITIVE_FIELD_RE = re.compile(
    r"(authorization|cookie|set-cookie|password|passwd|token|secret|api[_-]?key|access[_-]?key|private[_-]?key|key)$",
    re.I,
)
```

- [ ] **Step 4: Run full redaction tests**

Run:

```sh
.venv312/bin/python -m pytest tests/test_redaction.py tests/test_security_redaction.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```sh
git add app/trace/redaction.py tests/test_security_redaction.py
git commit -m "Harden redaction for cookie headers"
```

## Task 2: Run Finalization

**Files:**
- Modify: `app/storage/repositories.py`
- Modify: `app/gateway/openai_proxy.py`
- Test: `tests/test_openai_proxy_non_stream.py`
- Test: `tests/test_openai_proxy_stream.py`

- [ ] **Step 1: Add failing assertion for completed run**

In `tests/test_openai_proxy_non_stream.py`, after the proxy request:

```python
run = app_client.get("/api/runs/run_proxy").json()["run"]
assert run["status"] == "ok"
assert run["ended_at"]
```

- [ ] **Step 2: Run test to verify it fails**

```sh
.venv312/bin/python -m pytest tests/test_openai_proxy_non_stream.py -q
```

Expected: FAIL because `trace_runs.status` remains `running`.

- [ ] **Step 3: Add repository method**

Add to `Repository`:

```python
def update_run(self, run_id: str, data: dict[str, Any]) -> None:
    if not data:
        return
    assignments = ", ".join(f"{key}=:{key}" for key in data)
    values = dict(data)
    values["run_id"] = run_id
    with db_connection(self.db_path) as conn:
        conn.execute(f"UPDATE trace_runs SET {assignments} WHERE run_id=:run_id", values)
```

- [ ] **Step 4: Finalize run from `_finish_call()`**

In `app/gateway/openai_proxy.py`, after `repo.update_llm_call(...)`:

```python
repo.update_run(str(ctx["run_id"]), {
    "ended_at": ended_at,
    "status": status,
    "failure_type": type(error).__name__ if error else None,
})
```

Filter `None` values before passing to `update_run`.

- [ ] **Step 5: Run proxy tests**

```sh
.venv312/bin/python -m pytest tests/test_openai_proxy_non_stream.py tests/test_openai_proxy_stream.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```sh
git add app/storage/repositories.py app/gateway/openai_proxy.py tests/test_openai_proxy_non_stream.py tests/test_openai_proxy_stream.py
git commit -m "Finalize trace runs after LLM calls"
```

## Task 3: Streaming Usage Normalization

**Files:**
- Modify: `app/gateway/streaming_capture.py`
- Modify: `app/gateway/openai_proxy.py`
- Test: `tests/test_openai_proxy_stream.py`

- [ ] **Step 1: Extend stream test with final usage chunk**

Use a mock SSE body containing a final usage chunk:

```python
body = (
    b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
    b'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":4,"completion_tokens":2,"total_tokens":6}}\n\n'
    b'data: [DONE]\n\n'
)
```

Assert:

```python
assert calls[0]["input_tokens"] == 4
assert calls[0]["output_tokens"] == 2
assert calls[0]["total_tokens"] == 6
```

- [ ] **Step 2: Run test to verify it fails**

```sh
.venv312/bin/python -m pytest tests/test_openai_proxy_stream.py -q
```

Expected: FAIL because stream usage is not normalized.

- [ ] **Step 3: Add helper to extract usage from chunks**

In `app/gateway/streaming_capture.py`:

```python
def usage_from_record(record: dict[str, Any]) -> dict[str, int | None] | None:
    usage = (record.get("json") or {}).get("usage")
    if not usage:
        return None
    return {
        "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
        "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
```

- [ ] **Step 4: Track usage during stream iteration**

In the stream iterator, keep `stream_usage = {}` outside the iterator and update it when `usage_from_record(record)` returns data. Pass `usage=stream_usage or None` to `_finish_call()`.

- [ ] **Step 5: Run stream tests**

```sh
.venv312/bin/python -m pytest tests/test_openai_proxy_stream.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```sh
git add app/gateway/streaming_capture.py app/gateway/openai_proxy.py tests/test_openai_proxy_stream.py
git commit -m "Normalize token usage from streaming chunks"
```

## Task 4: Upstream Error Persistence

**Files:**
- Modify: `app/gateway/openai_proxy.py`
- Test: `tests/test_openai_proxy_errors.py`

- [ ] **Step 1: Write failing HTTP 500 test**

```python
import httpx
import respx


@respx.mock
def test_non_stream_upstream_500_is_recorded_as_error(app_client):
    respx.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": "upstream failed"})
    )

    response = app_client.post(
        "/v1/chat/completions",
        headers={"X-Trace-Id": "trace_error", "X-Run-Id": "run_error"},
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 500
    call = app_client.get("/api/traces/trace_error/llm-calls").json()["llm_calls"][0]
    assert call["status"] == "error"
    assert call["http_status"] == 500
    assert call["response_ref"]
    events = app_client.get("/api/traces/trace_error/events").json()["events"]
    assert any(event["event_type"] == "llm_error" for event in events)
```

- [ ] **Step 2: Run test to verify current behavior**

```sh
.venv312/bin/python -m pytest tests/test_openai_proxy_errors.py -q
```

Expected: If it passes, keep it as regression coverage. If it fails, update `_finish_call()` inputs so HTTP 500 produces `llm_error`.

- [ ] **Step 3: Ensure error body is archived**

In non-stream branch, keep writing `response_ref` before `_finish_call()` even when `upstream.status_code >= 400`.

- [ ] **Step 4: Run proxy tests**

```sh
.venv312/bin/python -m pytest tests/test_openai_proxy_non_stream.py tests/test_openai_proxy_errors.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```sh
git add app/gateway/openai_proxy.py tests/test_openai_proxy_errors.py
git commit -m "Record upstream HTTP errors"
```

## Task 5: Raw Path Traversal and Raw-View Denial Tests

**Files:**
- Modify: `tests/test_trace_api.py`
- Modify: `app/api/raw.py` only if tests expose a gap.

- [ ] **Step 1: Add path traversal test**

```python
def test_raw_api_blocks_path_traversal(app_client):
    response = app_client.get("/api/raw/../../../../etc/passwd")
    assert response.status_code == 400
```

- [ ] **Step 2: Add raw-view denial test**

```python
def test_raw_api_denies_raw_view_when_disabled(app_client, temp_data_dir):
    from app.trace.raw_store import RawStore

    ref = RawStore.from_env().write_json("trace_secret", "payload.json", {"authorization": "Bearer secret"})
    response = app_client.get(f"/api/raw/{ref}?raw=true")

    assert response.status_code == 200
    assert "secret" not in str(response.json())
```

- [ ] **Step 3: Run tests**

```sh
.venv312/bin/python -m pytest tests/test_trace_api.py -q
```

Expected: PASS. If traversal returns 404 instead of 400 due routing normalization, adjust the assertion to require non-200 and add a direct unit test for `RawStore._resolve()`.

- [ ] **Step 4: Commit**

```sh
git add tests/test_trace_api.py app/api/raw.py
git commit -m "Cover raw archive access controls"
```

## Task 6: Port and Operations Documentation Decision

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `scripts/dev.sh` only if the canonical port changes.

- [ ] **Step 1: Decide canonical port**

Choose one:

```text
Option A: keep 8080 because Hermes is already validated against it.
Option B: switch default to 43180 to match the handoff topology.
```

- [ ] **Step 2: If choosing 43180, update script default**

Change `scripts/dev.sh`:

```sh
uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-43180}" --reload
```

- [ ] **Step 3: Ensure README contains both migration note and final endpoint**

Required text:

```text
OpenClaw/Hermes should use http://127.0.0.1:<canonical-port>/v1.
Hub upstream should use http://127.0.0.1:4000.
LiteLLM should connect to the real model endpoint.
```

- [ ] **Step 4: Run verification**

```sh
.venv312/bin/python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```sh
git add README.md .env.example scripts/dev.sh
git commit -m "Document observation gateway operations"
```

## Self-Review

- Spec coverage: This plan covers Phase 1 stabilization items that are not already proven: redaction hardening, run finalization, stream usage, upstream errors, raw access controls, and operational docs.
- Gaps intentionally deferred: `external_ids`, OpenInference preview, importer strengthening, tool capture, failure labels, and eval replay belong to later phases.
- Placeholder scan: No implementation steps are left as unspecified work.
- Type consistency: Repository method names and field names match the current codebase.

