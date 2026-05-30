import sqlite3

import httpx
import respx

from app.storage.db import init_db
from app.storage.repositories import Repository


def test_external_ids_migration_is_idempotent(temp_data_dir):
    db_path = temp_data_dir / "hub.sqlite3"

    init_db(db_path)
    init_db(db_path)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "select name from sqlite_master where type='table' and name='external_ids'"
        ).fetchone()
    assert row is not None


@respx.mock
def test_non_stream_captures_inbound_and_upstream_correlations(app_client):
    respx.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
            headers={
                "content-type": "application/json",
                "x-litellm-call-id": "litellm-call-123",
                "llm_provider-trace-id": "provider-trace-456",
                "llm_provider-minimax-request-id": "minimax-request-789",
            },
        )
    )

    response = app_client.post(
        "/v1/chat/completions",
        headers={
            "X-Trace-Id": "trace_corr",
            "X-Run-Id": "run_corr",
            "X-Agent-Id": "hermes",
            "X-Session-Id": "hermes-session-123",
            "X-Channel": "desktop",
            "X-Conversation-Id": "conv-456",
            "Authorization": "Bearer should-not-persist",
            "Cookie": "session=should-not-persist",
            "X-Api-Key": "should-not-persist",
        },
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    correlations = app_client.get("/api/traces/trace_corr/correlations").json()["correlations"]
    pairs = {(item["source"], item["key"], item["value"]) for item in correlations}
    assert ("hermes", "agent_id", "hermes") in pairs
    assert ("hermes", "session_id", "hermes-session-123") in pairs
    assert ("hermes", "channel", "desktop") in pairs
    assert ("hermes", "conversation_id", "conv-456") in pairs
    assert ("litellm", "litellm_call_id", "litellm-call-123") in pairs
    assert ("minimax", "provider_trace_id", "provider-trace-456") in pairs
    assert ("minimax", "minimax_request_id", "minimax-request-789") in pairs
    assert "should-not-persist" not in str(correlations)


@respx.mock
def test_stream_captures_upstream_correlation_headers(app_client):
    body = b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'
    respx.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            content=body,
            headers={"content-type": "text/event-stream", "x-litellm-call-id": "litellm-stream-123"},
        )
    )

    response = app_client.post(
        "/v1/chat/completions",
        headers={"X-Trace-Id": "trace_stream_corr", "X-Run-Id": "run_stream_corr"},
        json={"model": "gpt-test", "stream": True, "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    correlations = app_client.get("/api/traces/trace_stream_corr/correlations").json()["correlations"]
    assert any(item["source"] == "litellm" and item["value"] == "litellm-stream-123" for item in correlations)


def test_correlation_lookup_and_duplicates(app_client):
    repo = Repository.from_env()
    data = {
        "trace_id": "trace_lookup",
        "run_id": "run_lookup",
        "llm_call_id": "llm_lookup",
        "source": "hermes",
        "key": "session_id",
        "value": "session-lookup",
    }
    repo.insert_external_id(data)
    repo.insert_external_id(data)

    trace_response = app_client.get("/api/traces/trace_lookup/correlations")
    lookup_response = app_client.get("/api/correlations?source=hermes&key=session_id&value=session-lookup")

    assert trace_response.status_code == 200
    assert len(trace_response.json()["correlations"]) == 1
    assert lookup_response.status_code == 200
    assert lookup_response.json()["matches"][0]["trace_id"] == "trace_lookup"


def test_trace_ui_shows_correlation_panel(app_client):
    repo = Repository.from_env()
    repo.upsert_run({"run_id": "run_ui_corr", "trace_id": "trace_ui_corr", "started_at": "2026-01-01T00:00:00Z", "status": "ok"})
    repo.insert_external_id({
        "trace_id": "trace_ui_corr",
        "run_id": "run_ui_corr",
        "source": "hermes",
        "key": "session_id",
        "value": "session-ui",
    })

    response = app_client.get("/traces/trace_ui_corr")

    assert response.status_code == 200
    assert "Correlations" in response.text
    assert "hermes" in response.text
    assert "session-ui" in response.text
