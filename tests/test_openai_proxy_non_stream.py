import httpx
import respx


@respx.mock
def test_non_stream_proxy_records_and_returns_upstream_response(app_client):
    respx.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl_1",
                "model": "gpt-test",
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            },
            headers={"content-type": "application/json"},
        )
    )

    response = app_client.post(
        "/v1/chat/completions",
        headers={"X-Trace-Id": "trace_proxy", "X-Run-Id": "run_proxy", "Authorization": "Bearer client-secret"},
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    assert response.headers["X-Trace-Id"] == "trace_proxy"
    assert response.headers["X-Run-Id"] == "run_proxy"
    assert response.headers["X-LLM-Call-Id"].startswith("llm_")

    calls = app_client.get("/api/traces/trace_proxy/llm-calls").json()["llm_calls"]
    assert calls[0]["status"] == "ok"
    assert calls[0]["total_tokens"] == 5
    run = app_client.get("/api/runs/run_proxy").json()["run"]
    assert run["status"] == "ok"
    assert run["ended_at"]
