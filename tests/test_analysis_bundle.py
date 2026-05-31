from fastapi.testclient import TestClient

from app.storage.repositories import Repository
from app.trace.ids import new_event_id
from app.trace.raw_store import RawStore


def _seed_run(repo: Repository, trace_id: str = "trace_bundle") -> None:
    repo.upsert_run({
        "run_id": "run_bundle",
        "trace_id": trace_id,
        "tenant_id": "local",
        "user_hash": "istale",
        "agent_id": "hermes",
        "session_id": "session_123",
        "channel": "discord",
        "conversation_id": "conversation_456",
        "identity_source": "ingress_route",
        "started_at": "2026-05-30T18:17:13Z",
        "status": "ok",
    })


def test_analysis_bundle_includes_non_stream_payloads_derived_text_and_correlations(app_client):
    repo = Repository.from_env()
    store = RawStore.from_env()
    _seed_run(repo)
    request_ref = store.write_json("trace_bundle", "request.json", {
        "headers": {"authorization": "Bearer secret-token"},
        "body": {"messages": [{"role": "user", "content": "天命（The Destiny）"}]},
    })
    response_ref = store.write_json("trace_bundle", "response.json", {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Readable answer.",
                "reasoning_content": "Reasoning answer.",
            }
        }]
    })
    repo.insert_event({
        "event_id": new_event_id(),
        "trace_id": "trace_bundle",
        "run_id": "run_bundle",
        "event_type": "llm_request",
        "source": "gateway",
        "timestamp": "2026-05-30T18:17:13Z",
        "payload_ref": request_ref,
    })
    repo.insert_llm_call({
        "llm_call_id": "llm_bundle",
        "trace_id": "trace_bundle",
        "run_id": "run_bundle",
        "tenant_id": "local",
        "user_hash": "istale",
        "agent_id": "hermes",
        "session_id": "session_123",
        "channel": "discord",
        "conversation_id": "conversation_456",
        "model": "MiniMax-M2.7",
        "endpoint": "/v1/chat/completions",
        "is_stream": 0,
        "started_at": "2026-05-30T18:17:13Z",
        "ended_at": "2026-05-30T18:17:15Z",
        "latency_ms": 1500,
        "status": "ok",
        "http_status": 200,
        "input_tokens": 10,
        "output_tokens": 20,
        "total_tokens": 30,
        "request_ref": request_ref,
        "response_ref": response_ref,
        "identity_source": "ingress_route",
    })
    repo.insert_external_id({
        "trace_id": "trace_bundle",
        "run_id": "run_bundle",
        "llm_call_id": "llm_bundle",
        "source": "litellm",
        "key": "litellm_call_id",
        "value": "call_123",
    })

    response = app_client.get("/api/traces/trace_bundle/analysis-bundle")

    assert response.status_code == 200
    bundle = response.json()
    assert bundle["trace_id"] == "trace_bundle"
    assert bundle["payload_mode"] == "redacted"
    assert bundle["identity"] == {
        "tenant_id": "local",
        "user_hash": "istale",
        "agent_id": "hermes",
        "session_id": "session_123",
        "channel": "discord",
        "conversation_id": "conversation_456",
        "identity_source": "ingress_route",
    }
    assert bundle["diagnostics"]["llm_call_count"] == 1
    assert bundle["diagnostics"]["event_count"] == 1
    assert bundle["diagnostics"]["correlation_count"] == 1
    assert bundle["diagnostics"]["has_raw_request"] is False
    assert bundle["timeline"][0]["event_type"] == "llm_request"
    assert bundle["correlations"][0]["value"] == "call_123"
    llm_call = bundle["llm_calls"][0]
    assert llm_call["metadata"]["llm_call_id"] == "llm_bundle"
    assert llm_call["metadata"]["model"] == "MiniMax-M2.7"
    assert llm_call["derived"]["assistant_text"] == "Readable answer."
    assert llm_call["derived"]["reasoning_text"] == "Reasoning answer."
    assert "secret-token" not in str(llm_call["payloads"]["request"])
    assert "[REDACTED]" in str(llm_call["payloads"]["request"])


def test_analysis_bundle_includes_raw_payloads_when_payload_mode_is_raw(tmp_path, monkeypatch):
    monkeypatch.setenv("AOH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AOH_DATABASE_PATH", str(tmp_path / "data" / "hub.sqlite3"))
    monkeypatch.setenv("UPSTREAM_OPENAI_BASE_URL", "http://upstream.test")
    monkeypatch.setenv("AOH_PAYLOAD_MODE", "raw")

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    repo = Repository.from_env()
    store = RawStore.from_env()
    _seed_run(repo)
    request_ref = store.write_json("trace_bundle", "request.json", {
        "headers": {"authorization": "Bearer secret-token"},
        "body": {"messages": [{"role": "user", "content": "天命（The Destiny）"}]},
    })
    repo.insert_llm_call({
        "llm_call_id": "llm_bundle",
        "trace_id": "trace_bundle",
        "run_id": "run_bundle",
        "model": "MiniMax-M2.7",
        "endpoint": "/v1/chat/completions",
        "started_at": "2026-05-30T18:17:13Z",
        "status": "ok",
        "request_ref": request_ref,
    })

    with TestClient(app) as client:
        response = client.get("/api/traces/trace_bundle/analysis-bundle")

    assert response.status_code == 200
    bundle = response.json()
    assert bundle["payload_mode"] == "raw"
    assert bundle["diagnostics"]["has_raw_request"] is True
    rendered = str(bundle["llm_calls"][0]["payloads"]["request"])
    assert "Bearer secret-token" in rendered
    assert "天命（The Destiny）" in rendered


def test_analysis_bundle_combines_stream_chunks(app_client):
    repo = Repository.from_env()
    store = RawStore.from_env()
    _seed_run(repo, trace_id="trace_stream_bundle")
    request_ref = store.write_json("trace_stream_bundle", "request.json", {"body": {"stream": True}})
    chunks_ref = store.append_jsonl("trace_stream_bundle", "chunks.jsonl", {
        "raw": 'data: {"choices":[{"delta":{"reasoning_content":"Think "}}]}\n\n'
    })
    store.append_jsonl("trace_stream_bundle", "chunks.jsonl", {
        "raw": 'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
    })
    store.append_jsonl("trace_stream_bundle", "chunks.jsonl", {"raw": "data: [DONE]\n\n"})
    repo.insert_llm_call({
        "llm_call_id": "llm_stream_bundle",
        "trace_id": "trace_stream_bundle",
        "run_id": "run_bundle",
        "model": "MiniMax-M2.7",
        "endpoint": "/v1/chat/completions",
        "is_stream": 1,
        "started_at": "2026-05-30T18:17:13Z",
        "status": "ok",
        "request_ref": request_ref,
        "response_chunks_ref": chunks_ref,
    })

    response = app_client.get("/api/traces/trace_stream_bundle/analysis-bundle")

    assert response.status_code == 200
    llm_call = response.json()["llm_calls"][0]
    assert len(llm_call["payloads"]["response_chunks"]) == 3
    assert llm_call["derived"]["assistant_text"] == "Hello"
    assert llm_call["derived"]["reasoning_text"] == "Think "
    assert response.json()["diagnostics"]["has_stream_chunks"] is True


def test_analysis_bundle_records_missing_payload_warning(app_client):
    repo = Repository.from_env()
    _seed_run(repo, trace_id="trace_missing_payload")
    repo.insert_llm_call({
        "llm_call_id": "llm_missing_payload",
        "trace_id": "trace_missing_payload",
        "run_id": "run_bundle",
        "model": "MiniMax-M2.7",
        "endpoint": "/v1/chat/completions",
        "started_at": "2026-05-30T18:17:13Z",
        "status": "ok",
        "request_ref": "missing/request.json",
    })

    response = app_client.get("/api/traces/trace_missing_payload/analysis-bundle")

    assert response.status_code == 200
    bundle = response.json()
    assert bundle["llm_calls"][0]["payloads"] == {}
    assert "missing request payload: missing/request.json" in bundle["diagnostics"]["warnings"]


def test_analysis_bundle_rejects_payload_ref_path_traversal(app_client):
    repo = Repository.from_env()
    _seed_run(repo, trace_id="trace_bad_ref")
    repo.insert_llm_call({
        "llm_call_id": "llm_bad_ref",
        "trace_id": "trace_bad_ref",
        "run_id": "run_bundle",
        "model": "MiniMax-M2.7",
        "endpoint": "/v1/chat/completions",
        "started_at": "2026-05-30T18:17:13Z",
        "status": "ok",
        "request_ref": "../../../../etc/passwd",
    })

    response = app_client.get("/api/traces/trace_bad_ref/analysis-bundle")

    assert response.status_code == 400
    assert "escapes raw archive" in response.json()["detail"]


def test_analysis_bundle_returns_404_for_unknown_trace(app_client):
    response = app_client.get("/api/traces/not_found/analysis-bundle")

    assert response.status_code == 404
    assert response.json()["detail"] == "trace not found"
