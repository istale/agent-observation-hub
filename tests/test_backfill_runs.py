from app.maintenance.backfill_runs import backfill_running_runs
from app.storage.repositories import Repository


def test_backfill_dry_run_does_not_update_terminal_running_run(temp_data_dir):
    db_path = temp_data_dir / "hub.sqlite3"
    repo = Repository(db_path)
    repo.upsert_run({"run_id": "run_terminal", "trace_id": "trace_terminal", "started_at": "2026-01-01T00:00:00Z", "status": "running"})
    repo.insert_llm_call({
        "llm_call_id": "llm_terminal",
        "trace_id": "trace_terminal",
        "run_id": "run_terminal",
        "endpoint": "/v1/chat/completions",
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:02Z",
        "status": "ok",
    })

    summary = backfill_running_runs(db_path, apply=False)

    assert summary.finalized_ok == 1
    assert repo.get_run("run_terminal")["status"] == "running"


def test_backfill_updates_running_run_from_terminal_llm_call(temp_data_dir):
    db_path = temp_data_dir / "hub.sqlite3"
    repo = Repository(db_path)
    repo.upsert_run({"run_id": "run_terminal", "trace_id": "trace_terminal", "started_at": "2026-01-01T00:00:00Z", "status": "running"})
    repo.insert_llm_call({
        "llm_call_id": "llm_terminal",
        "trace_id": "trace_terminal",
        "run_id": "run_terminal",
        "endpoint": "/v1/chat/completions",
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:02Z",
        "status": "ok",
    })

    summary = backfill_running_runs(db_path, apply=True)

    run = repo.get_run("run_terminal")
    assert summary.finalized_ok == 1
    assert run["status"] == "ok"
    assert run["ended_at"] == "2026-01-01T00:00:02Z"


def test_backfill_cancels_stale_running_call_and_run(temp_data_dir):
    db_path = temp_data_dir / "hub.sqlite3"
    repo = Repository(db_path)
    repo.upsert_run({"run_id": "run_stale", "trace_id": "trace_stale", "started_at": "2026-01-01T00:00:00Z", "status": "running"})
    repo.insert_llm_call({
        "llm_call_id": "llm_stale",
        "trace_id": "trace_stale",
        "run_id": "run_stale",
        "endpoint": "/v1/chat/completions",
        "started_at": "2026-01-01T00:00:00Z",
        "status": "running",
    })

    summary = backfill_running_runs(db_path, stale_minutes=60, apply=True)

    run = repo.get_run("run_stale")
    call = repo.get_llm_call("llm_stale")
    assert summary.cancelled_stale_calls == 1
    assert summary.cancelled_stale_runs == 1
    assert run["status"] == "error"
    assert run["failure_type"] == "stale_running_run"
    assert call["status"] == "cancelled"
    assert call["error_type"] == "stale_running_call"
