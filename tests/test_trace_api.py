from app.storage.repositories import Repository
from app.trace.ids import new_event_id
from app.trace.raw_store import RawStore


def test_trace_api_returns_persisted_trace_and_redacted_raw(app_client, temp_data_dir):
    repo = Repository.from_env()
    store = RawStore.from_env()
    ref = store.write_json("trace_api", "payload.json", {"email": "a@example.com"})
    repo.upsert_run({"run_id": "run_api", "trace_id": "trace_api", "started_at": "2026-01-01T00:00:00Z", "status": "running"})
    repo.insert_event({
        "event_id": new_event_id(),
        "trace_id": "trace_api",
        "run_id": "run_api",
        "event_type": "llm_request",
        "source": "gateway",
        "timestamp": "2026-01-01T00:00:00Z",
        "payload_ref": ref,
    })

    trace = app_client.get("/api/traces/trace_api")
    raw = app_client.get(f"/api/raw/{ref}")

    assert trace.status_code == 200
    assert trace.json()["run"]["trace_id"] == "trace_api"
    assert raw.status_code == 200
    assert "a@example.com" not in str(raw.json())


def test_raw_api_returns_redacted_payload_when_payload_mode_is_redacted(app_client, temp_data_dir):
    store = RawStore.from_env()
    ref = store.write_json("trace_secret", "payload.json", {"authorization": "Bearer secret"})

    response = app_client.get(f"/api/raw/{ref}?raw=true")

    assert response.status_code == 200
    assert "secret" not in str(response.json())


def test_raw_api_returns_raw_when_payload_mode_is_raw(tmp_path, monkeypatch):
    monkeypatch.setenv("AOH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AOH_DATABASE_PATH", str(tmp_path / "data" / "hub.sqlite3"))
    monkeypatch.setenv("UPSTREAM_OPENAI_BASE_URL", "http://upstream.test")
    monkeypatch.setenv("ALLOW_RAW_VIEW", "false")
    monkeypatch.setenv("AOH_PAYLOAD_MODE", "raw")

    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    store = RawStore.from_env()
    ref = store.write_json("trace_raw_policy", "payload.json", {
        "authorization": "Bearer secret-token",
        "body": {"messages": [{"role": "user", "content": "天命（The Destiny）"}]},
    })

    with TestClient(app) as client:
        response = client.get(f"/api/raw/{ref}")

    assert response.status_code == 200
    rendered = str(response.json())
    assert "Bearer secret-token" in rendered
    assert "天命（The Destiny）" in rendered


def test_raw_api_falls_back_to_redacted_for_invalid_payload_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("AOH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AOH_DATABASE_PATH", str(tmp_path / "data" / "hub.sqlite3"))
    monkeypatch.setenv("UPSTREAM_OPENAI_BASE_URL", "http://upstream.test")
    monkeypatch.setenv("AOH_PAYLOAD_MODE", "invalid")

    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    store = RawStore.from_env()
    ref = store.write_json("trace_invalid_policy", "payload.json", {"authorization": "Bearer secret-token"})

    with TestClient(app) as client:
        response = client.get(f"/api/raw/{ref}")

    assert response.status_code == 200
    assert "secret-token" not in str(response.json())
    assert "[REDACTED]" in str(response.json())


def test_raw_store_blocks_path_traversal(temp_data_dir):
    store = RawStore.from_env()

    try:
        store.read("../../../../etc/passwd")
    except ValueError as exc:
        assert "escapes raw archive" in str(exc)
    else:
        raise AssertionError("path traversal should be blocked")
