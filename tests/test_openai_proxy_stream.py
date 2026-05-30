import httpx
import respx


@respx.mock
def test_stream_proxy_forwards_sse_and_records_chunks(app_client):
    body = b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'
    respx.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})
    )

    response = app_client.post(
        "/v1/chat/completions",
        headers={"X-Trace-Id": "trace_stream", "X-Run-Id": "run_stream"},
        json={"model": "gpt-test", "stream": True, "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    assert "data:" in response.text
    calls = app_client.get("/api/traces/trace_stream/llm-calls").json()["llm_calls"]
    assert calls[0]["status"] == "ok"
    assert calls[0]["response_chunks_ref"]
