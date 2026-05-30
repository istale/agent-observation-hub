from app.storage.repositories import Repository
from app.trace.raw_store import RawStore


def test_index_ui_renders(app_client):
    response = app_client.get("/")

    assert response.status_code == 200
    assert "Agent Observation Hub" in response.text


def test_taipei_time_filter_renders_utc_as_local_time(app_client):
    response = app_client.get("/")

    assert response.status_code == 200
    template_env = response.template.environment

    assert template_env.filters["taipei_time"]("2026-05-30T09:11:18.025956Z") == "2026-05-30 17:11:18 Taipei"
    assert template_env.filters["taipei_time"](None) == ""


def test_llm_call_ui_shows_readable_response_sections(app_client):
    repo = Repository.from_env()
    store = RawStore.from_env()
    request_ref = store.write_json("trace_ui", "request.json", {"body": {"messages": [{"role": "user", "content": "Hi"}]}})
    response_ref = store.write_json("trace_ui", "response.json", {
        "choices": [{
            "message": {
                "content": "Hello from the assistant.",
                "reasoning_content": "I should answer briefly.",
            }
        }]
    })
    repo.upsert_run({"run_id": "run_ui", "trace_id": "trace_ui", "started_at": "2026-05-30T09:11:18Z", "status": "ok"})
    repo.insert_llm_call({
        "llm_call_id": "llm_ui",
        "trace_id": "trace_ui",
        "run_id": "run_ui",
        "model": "MiniMax-M2.7",
        "endpoint": "/v1/chat/completions",
        "is_stream": 0,
        "started_at": "2026-05-30T09:11:18Z",
        "ended_at": "2026-05-30T09:11:19Z",
        "status": "ok",
        "request_ref": request_ref,
        "response_ref": response_ref,
    })

    response = app_client.get("/llm-calls/llm_ui")

    assert response.status_code == 200
    assert "2026-05-30 17:11:18 Taipei" in response.text
    assert "Hello from the assistant." in response.text
    assert "I should answer briefly." in response.text
    assert "Readable Response" in response.text


def test_llm_call_ui_combines_stream_chunks(app_client):
    repo = Repository.from_env()
    store = RawStore.from_env()
    request_ref = store.write_json("trace_stream_ui", "request.json", {"body": {"stream": True}})
    chunks_ref = store.append_jsonl("trace_stream_ui", "chunks.jsonl", {
        "raw": 'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
    })
    store.append_jsonl("trace_stream_ui", "chunks.jsonl", {
        "raw": 'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
    })
    store.append_jsonl("trace_stream_ui", "chunks.jsonl", {"raw": "data: [DONE]\n\n"})
    repo.upsert_run({"run_id": "run_stream_ui", "trace_id": "trace_stream_ui", "started_at": "2026-05-30T09:11:18Z", "status": "ok"})
    repo.insert_llm_call({
        "llm_call_id": "llm_stream_ui",
        "trace_id": "trace_stream_ui",
        "run_id": "run_stream_ui",
        "model": "MiniMax-M2.7",
        "endpoint": "/v1/chat/completions",
        "is_stream": 1,
        "started_at": "2026-05-30T09:11:18Z",
        "ended_at": "2026-05-30T09:11:19Z",
        "status": "ok",
        "request_ref": request_ref,
        "response_chunks_ref": chunks_ref,
    })

    response = app_client.get("/llm-calls/llm_stream_ui")

    assert response.status_code == 200
    assert "Hello" in response.text
    assert "Stream Chunks" in response.text
