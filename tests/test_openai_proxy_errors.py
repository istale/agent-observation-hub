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
    assert call["error_message"]
    assert call["response_ref"]
    events = app_client.get("/api/traces/trace_error/events").json()["events"]
    assert any(event["event_type"] == "llm_error" for event in events)


@respx.mock
def test_transport_error_records_request_and_marks_run_error(app_client):
    respx.post("http://upstream.test/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    response = app_client.post(
        "/v1/chat/completions",
        headers={"X-Trace-Id": "trace_transport_error", "X-Run-Id": "run_transport_error"},
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 502
    call = app_client.get("/api/traces/trace_transport_error/llm-calls").json()["llm_calls"][0]
    assert call["status"] == "error"
    assert call["request_ref"]
    assert call["error_type"] == "ConnectError"
    assert call["error_message"]
    run = app_client.get("/api/runs/run_transport_error").json()["run"]
    assert run["status"] == "error"
    assert run["ended_at"]
