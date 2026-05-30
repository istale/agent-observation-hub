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


def test_raw_api_denies_raw_view_when_disabled(app_client, temp_data_dir):
    store = RawStore.from_env()
    ref = store.write_json("trace_secret", "payload.json", {"authorization": "Bearer secret"})

    response = app_client.get(f"/api/raw/{ref}?raw=true")

    assert response.status_code == 200
    assert "secret" not in str(response.json())


def test_raw_store_blocks_path_traversal(temp_data_dir):
    store = RawStore.from_env()

    try:
        store.read("../../../../etc/passwd")
    except ValueError as exc:
        assert "escapes raw archive" in str(exc)
    else:
        raise AssertionError("path traversal should be blocked")
