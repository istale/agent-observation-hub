import asyncio

import httpx
import respx


class DisconnectingStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        raise asyncio.CancelledError()


@respx.mock
def test_stream_proxy_forwards_sse_and_records_chunks(app_client):
    body = (
        b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        b'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":4,"completion_tokens":2,"total_tokens":6}}\n\n'
        b'data: [DONE]\n\n'
    )
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
    assert calls[0]["input_tokens"] == 4
    assert calls[0]["output_tokens"] == 2
    assert calls[0]["total_tokens"] == 6


@respx.mock
def test_stream_cancellation_marks_call_and_run_error(app_client):
    respx.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            stream=DisconnectingStream(),
            headers={"content-type": "text/event-stream"},
        )
    )

    app_client.post(
        "/v1/chat/completions",
        headers={"X-Trace-Id": "trace_stream_cancel", "X-Run-Id": "run_stream_cancel"},
        json={"model": "gpt-test", "stream": True, "messages": [{"role": "user", "content": "hello"}]},
    )

    call = app_client.get("/api/traces/trace_stream_cancel/llm-calls").json()["llm_calls"][0]
    assert call["status"] == "error"
    assert call["error_type"] == "CancelledError"
    assert call["response_chunks_ref"]
    run = app_client.get("/api/runs/run_stream_cancel").json()["run"]
    assert run["status"] == "error"
    assert run["ended_at"]
