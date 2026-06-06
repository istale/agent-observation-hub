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


def test_llm_call_ui_renders_unicode_json_readably(app_client):
    repo = Repository.from_env()
    store = RawStore.from_env()
    request_ref = store.write_json("trace_unicode_ui", "request.json", {
        "body": {
            "messages": [
                {"role": "user", "content": "天命（The Destiny）\n\n「讓我可讀」"}
            ]
        }
    })
    response_ref = store.write_json("trace_unicode_ui", "response.json", {
        "choices": [{"message": {"role": "assistant", "content": "收到天命。"}}]
    })
    repo.upsert_run({"run_id": "run_unicode_ui", "trace_id": "trace_unicode_ui", "started_at": "2026-05-30T09:11:18Z", "status": "ok"})
    repo.insert_llm_call({
        "llm_call_id": "llm_unicode_ui",
        "trace_id": "trace_unicode_ui",
        "run_id": "run_unicode_ui",
        "model": "MiniMax-M2.7",
        "endpoint": "/v1/chat/completions",
        "started_at": "2026-05-30T09:11:18Z",
        "status": "ok",
        "request_ref": request_ref,
        "response_ref": response_ref,
    })

    response = app_client.get("/llm-calls/llm_unicode_ui")

    assert response.status_code == 200
    assert "天命（The Destiny）" in response.text
    assert "\\u5929\\u547d" not in response.text


def test_llm_call_ui_shows_raw_payload_when_payload_mode_is_raw(tmp_path, monkeypatch):
    monkeypatch.setenv("AOH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AOH_DATABASE_PATH", str(tmp_path / "data" / "hub.sqlite3"))
    monkeypatch.setenv("UPSTREAM_OPENAI_BASE_URL", "http://upstream.test")
    monkeypatch.setenv("AOH_PAYLOAD_MODE", "raw")

    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    repo = Repository.from_env()
    store = RawStore.from_env()
    request_ref = store.write_json("trace_raw_ui", "request.json", {
        "headers": {"authorization": "Bearer secret-token"},
        "body": {"messages": [{"role": "user", "content": "天命（The Destiny）"}]},
    })
    response_ref = store.write_json("trace_raw_ui", "response.json", {
        "choices": [{"message": {"role": "assistant", "content": "收到天命。"}}]
    })
    repo.upsert_run({"run_id": "run_raw_ui", "trace_id": "trace_raw_ui", "started_at": "2026-05-30T09:11:18Z", "status": "ok"})
    repo.insert_llm_call({
        "llm_call_id": "llm_raw_ui",
        "trace_id": "trace_raw_ui",
        "run_id": "run_raw_ui",
        "model": "MiniMax-M2.7",
        "endpoint": "/v1/chat/completions",
        "started_at": "2026-05-30T09:11:18Z",
        "status": "ok",
        "request_ref": request_ref,
        "response_ref": response_ref,
    })

    with TestClient(app) as client:
        response = client.get("/llm-calls/llm_raw_ui")

    assert response.status_code == 200
    assert "Payload mode: raw" in response.text
    assert "Raw Request JSON" in response.text
    assert "Bearer secret-token" in response.text
    assert "天命（The Destiny）" in response.text
    assert "Redacted Request" not in response.text


def test_llm_call_ui_shows_redacted_payload_when_payload_mode_is_redacted(app_client):
    repo = Repository.from_env()
    store = RawStore.from_env()
    request_ref = store.write_json("trace_redacted_ui", "request.json", {
        "headers": {"authorization": "Bearer secret-token"},
        "body": {"messages": [{"role": "user", "content": "Hi"}]},
    })
    repo.upsert_run({"run_id": "run_redacted_ui", "trace_id": "trace_redacted_ui", "started_at": "2026-05-30T09:11:18Z", "status": "ok"})
    repo.insert_llm_call({
        "llm_call_id": "llm_redacted_ui",
        "trace_id": "trace_redacted_ui",
        "run_id": "run_redacted_ui",
        "model": "MiniMax-M2.7",
        "endpoint": "/v1/chat/completions",
        "started_at": "2026-05-30T09:11:18Z",
        "status": "ok",
        "request_ref": request_ref,
    })

    response = app_client.get("/llm-calls/llm_redacted_ui")

    assert response.status_code == 200
    assert "Payload mode: redacted" in response.text
    assert "Redacted Request JSON" in response.text
    assert "secret-token" not in response.text
    assert "[REDACTED]" in response.text


def test_trace_ui_orders_sections_timeline_calls_correlations(app_client):
    repo = Repository.from_env()
    repo.upsert_run({"run_id": "run_order_ui", "trace_id": "trace_order_ui", "started_at": "2026-05-30T09:11:18Z", "status": "ok"})

    response = app_client.get("/traces/trace_order_ui")

    assert response.status_code == 200
    # Section headings now include explanatory text + tooltips per the UI doc spec;
    # match by leading "<h2>Section" prefix only.
    assert response.text.index("<h2>Timeline") < response.text.index("<h2>LLM Calls")
    assert response.text.index("<h2>LLM Calls") < response.text.index("<h2>Correlations")


def test_trace_ui_embeds_expanded_readable_llm_response_and_reasoning(app_client):
    repo = Repository.from_env()
    store = RawStore.from_env()
    request_ref = store.write_json("trace_embedded_ui", "request.json", {"body": {"messages": [{"role": "user", "content": "Hi"}]}})
    response_ref = store.write_json("trace_embedded_ui", "response.json", {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Embedded assistant text.",
                "reasoning_content": "Embedded reasoning text.",
            }
        }]
    })
    repo.upsert_run({"run_id": "run_embedded_ui", "trace_id": "trace_embedded_ui", "started_at": "2026-05-30T09:11:18Z", "status": "ok"})
    repo.insert_llm_call({
        "llm_call_id": "llm_embedded_ui",
        "trace_id": "trace_embedded_ui",
        "run_id": "run_embedded_ui",
        "model": "MiniMax-M2.7",
        "endpoint": "/v1/chat/completions",
        "started_at": "2026-05-30T09:11:18Z",
        "ended_at": "2026-05-30T09:11:19Z",
        "latency_ms": 1000,
        "status": "ok",
        "request_ref": request_ref,
        "response_ref": response_ref,
    })

    response = app_client.get("/traces/trace_embedded_ui")

    assert response.status_code == 200
    assert "<details open" in response.text
    assert "Embedded assistant text." in response.text
    assert "Embedded reasoning text." in response.text
    assert "/llm-calls/llm_embedded_ui" in response.text
