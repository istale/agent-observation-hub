from fastapi.testclient import TestClient

from app.storage.repositories import Repository
from app.trace.raw_store import RawStore


def _insert_run(repo: Repository, *, trace_id: str, run_id: str, user_hash: str = "istale", agent_id: str = "hermes", channel: str = "discord", started_at: str, status: str = "ok") -> None:
    repo.upsert_run({
        "run_id": run_id,
        "trace_id": trace_id,
        "tenant_id": "local",
        "user_hash": user_hash,
        "agent_id": agent_id,
        "channel": channel,
        "started_at": started_at,
        "ended_at": started_at,
        "status": status,
        "identity_source": "ingress_route",
    })


def _insert_llm_call(
    repo: Repository,
    *,
    store: RawStore,
    trace_id: str,
    run_id: str,
    user_hash: str = "istale",
    agent_id: str = "hermes",
    channel: str = "discord",
    started_at: str,
    total_tokens: int,
    latency_ms: int,
    content: str,
) -> None:
    request_ref = store.write_json(trace_id, f"{trace_id}_request.json", {
        "headers": {"authorization": "Bearer secret-token"},
        "body": {"messages": [{"role": "user", "content": f"Question for {trace_id}"}]},
    })
    response_ref = store.write_json(trace_id, f"{trace_id}_response.json", {
        "choices": [{"message": {"role": "assistant", "content": content}}]
    })
    repo.insert_llm_call({
        "llm_call_id": f"llm_{trace_id}",
        "trace_id": trace_id,
        "run_id": run_id,
        "tenant_id": "local",
        "user_hash": user_hash,
        "agent_id": agent_id,
        "channel": channel,
        "model": "MiniMax-M2.7",
        "endpoint": "/v1/chat/completions",
        "started_at": started_at,
        "ended_at": started_at,
        "latency_ms": latency_ms,
        "status": "ok",
        "http_status": 200,
        "total_tokens": total_tokens,
        "request_ref": request_ref,
        "response_ref": response_ref,
        "identity_source": "ingress_route",
    })


def test_user_analysis_bundle_returns_summary_without_payloads_by_default(app_client):
    repo = Repository.from_env()
    store = RawStore.from_env()
    _insert_run(repo, trace_id="trace_1", run_id="run_1", started_at="2026-05-31T10:00:00Z")
    _insert_run(repo, trace_id="trace_2", run_id="run_2", started_at="2026-05-31T11:00:00Z")
    _insert_llm_call(repo, store=store, trace_id="trace_1", run_id="run_1", started_at="2026-05-31T10:00:00Z", total_tokens=100, latency_ms=500, content="First answer.")
    _insert_llm_call(repo, store=store, trace_id="trace_2", run_id="run_2", started_at="2026-05-31T11:00:00Z", total_tokens=200, latency_ms=900, content="Second answer.")

    response = app_client.get("/api/subjects/users/istale/analysis-bundle?limit=10")

    assert response.status_code == 200
    bundle = response.json()
    assert bundle["subject"] == {"user_hash": "istale"}
    assert bundle["filters"]["include_payloads"] is False
    assert bundle["summary"]["trace_count"] == 2
    assert bundle["summary"]["llm_call_count"] == 2
    assert bundle["summary"]["total_tokens"] == 300
    assert bundle["summary"]["max_latency_ms"] == 900
    assert bundle["summary"]["statuses"] == {"ok": 2}
    assert bundle["summary"]["agents"] == [{"agent_id": "hermes", "channel": "discord", "trace_count": 2}]
    assert [item["trace_id"] for item in bundle["traces"]] == ["trace_2", "trace_1"]
    assert bundle["traces"][0]["llm_calls"][0]["derived"]["assistant_text"] == "Second answer."
    assert "payloads" not in bundle["traces"][0]["llm_calls"][0]
    assert bundle["traces"][0]["llm_calls"][0]["payload_refs"]["request_ref"]


def test_user_analysis_bundle_include_payloads_follows_raw_payload_mode(tmp_path, monkeypatch):
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
    _insert_run(repo, trace_id="trace_raw", run_id="run_raw", started_at="2026-05-31T10:00:00Z")
    _insert_llm_call(repo, store=store, trace_id="trace_raw", run_id="run_raw", started_at="2026-05-31T10:00:00Z", total_tokens=100, latency_ms=500, content="Raw answer.")

    with TestClient(app) as client:
        response = client.get("/api/subjects/users/istale/analysis-bundle?include_payloads=true")

    assert response.status_code == 200
    llm_call = response.json()["traces"][0]["llm_calls"][0]
    assert "payloads" in llm_call
    assert "Bearer secret-token" in str(llm_call["payloads"]["request"])


def test_user_analysis_bundle_filters_traces(app_client):
    repo = Repository.from_env()
    store = RawStore.from_env()
    _insert_run(repo, trace_id="trace_keep", run_id="run_keep", started_at="2026-05-31T10:00:00Z", agent_id="hermes", channel="discord", status="ok")
    _insert_run(repo, trace_id="trace_other_agent", run_id="run_other_agent", started_at="2026-05-31T09:00:00Z", agent_id="openclaw", channel="discord", status="ok")
    _insert_run(repo, trace_id="trace_other_status", run_id="run_other_status", started_at="2026-05-31T08:00:00Z", agent_id="hermes", channel="discord", status="error")
    _insert_llm_call(repo, store=store, trace_id="trace_keep", run_id="run_keep", started_at="2026-05-31T10:00:00Z", total_tokens=100, latency_ms=500, content="Keep answer.")

    response = app_client.get("/api/subjects/users/istale/analysis-bundle?agent_id=hermes&channel=discord&status=ok&limit=5")

    assert response.status_code == 200
    bundle = response.json()
    assert [item["trace_id"] for item in bundle["traces"]] == ["trace_keep"]
    assert bundle["filters"]["agent_id"] == "hermes"
    assert bundle["filters"]["channel"] == "discord"
    assert bundle["filters"]["status"] == "ok"


def test_user_analysis_bundle_unknown_user_returns_empty_bundle(app_client):
    response = app_client.get("/api/subjects/users/missing/analysis-bundle")

    assert response.status_code == 200
    bundle = response.json()
    assert bundle["subject"] == {"user_hash": "missing"}
    assert bundle["summary"]["trace_count"] == 0
    assert bundle["traces"] == []
    assert bundle["diagnostics"]["warnings"] == ["no traces matched filters"]
