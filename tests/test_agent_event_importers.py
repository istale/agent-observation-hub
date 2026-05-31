import json
from pathlib import Path

from app.importers.agent_events.cli import run_import
from app.importers.agent_events.normalizer import parse_line
from app.importers.agent_events.roots import load_roots_config, paths_for_source
from app.storage.repositories import Repository


def test_hermes_json_line_parses_into_normalized_event():
    line = json.dumps({
        "event_type": "tool_call",
        "timestamp": "2026-05-31T10:00:00Z",
        "session_id": "session_123",
        "agent_id": "hermes",
        "channel": "discord",
        "message": "tool started",
        "payload": {"tool": "search"},
    })

    event = parse_line(line, source="hermes", user_hash="istale")

    assert event.source == "hermes"
    assert event.event_type == "tool_call"
    assert event.timestamp == "2026-05-31T10:00:00Z"
    assert event.user_hash == "istale"
    assert event.session_id == "session_123"
    assert event.payload == {"tool": "search"}


def test_plain_text_line_falls_back_to_external_log():
    event = parse_line("plain failure line", source="openclaw", user_hash="alice")

    assert event.event_type == "external_log"
    assert event.source == "openclaw"
    assert event.user_hash == "alice"
    assert event.payload == {"message": "plain failure line"}
    assert event.raw_line == "plain failure line"


def test_importer_dry_run_parses_without_writing_db(tmp_path, temp_data_dir):
    log_path = tmp_path / "hermes.log"
    log_path.write_text('{"event_type":"agent_message","message":"hello"}\n', encoding="utf-8")
    repo = Repository.from_env()

    result = run_import(source="hermes", paths=[log_path], dry_run=True, repo=repo)

    assert result["parsed"] == 1
    assert result["written"] == 0
    assert repo.list_events("anything") == []


def test_importer_writes_event_to_synthetic_trace_when_no_join(tmp_path, temp_data_dir):
    log_path = tmp_path / "hermes.log"
    log_path.write_text('{"event_type":"agent_message","timestamp":"2026-05-31T10:00:00Z","message":"hello","agent_id":"hermes"}\n', encoding="utf-8")
    repo = Repository.from_env()

    result = run_import(source="hermes", paths=[log_path], user_hash="istale", dry_run=False, repo=repo)

    assert result["parsed"] == 1
    assert result["written"] == 1
    runs = repo.list_runs(10)
    assert runs[0]["status"] == "external"
    assert runs[0]["trigger_type"] == "importer"
    assert runs[0]["user_hash"] == "istale"
    events = repo.list_events(runs[0]["trace_id"])
    assert events[0]["event_type"] == "agent_message"
    assert events[0]["source"] == "hermes"


def test_importer_joins_existing_trace_by_session_agent_and_time(tmp_path, temp_data_dir):
    log_path = tmp_path / "hermes.log"
    log_path.write_text('{"event_type":"tool_call","timestamp":"2026-05-31T10:05:00Z","session_id":"session_123","agent_id":"hermes"}\n', encoding="utf-8")
    repo = Repository.from_env()
    repo.upsert_run({
        "run_id": "run_existing",
        "trace_id": "trace_existing",
        "user_hash": "istale",
        "agent_id": "hermes",
        "session_id": "session_123",
        "channel": "discord",
        "started_at": "2026-05-31T10:00:00Z",
        "ended_at": "2026-05-31T10:06:00Z",
        "status": "ok",
    })

    result = run_import(source="hermes", paths=[log_path], user_hash="istale", repo=repo)

    assert result["written"] == 1
    assert repo.list_events("trace_existing")[0]["event_type"] == "tool_call"


def test_importer_fills_identity_from_ingress_route(tmp_path, temp_data_dir):
    log_path = tmp_path / "hermes.log"
    log_path.write_text('{"event_type":"agent_message","timestamp":"2026-05-31T10:00:00Z","message":"hello"}\n', encoding="utf-8")
    repo = Repository.from_env()
    repo.insert_ingress_route({
        "listen_host": "127.0.0.1",
        "listen_port": 43180,
        "path_prefix": "/v1",
        "tenant_id": "local",
        "user_hash": "istale",
        "agent_id": "hermes",
        "channel": "discord",
        "enabled": 1,
    })

    result = run_import(source="hermes", paths=[log_path], user_hash="istale", repo=repo)

    run = repo.list_runs(10)[0]
    assert result["written"] == 1
    assert run["tenant_id"] == "local"
    assert run["agent_id"] == "hermes"
    assert run["channel"] == "discord"
    assert run["identity_source"] == "ingress_route"


def test_roots_config_discovers_source_paths(tmp_path):
    roots_path = tmp_path / "roots.json"
    hermes_root = tmp_path / ".hermes"
    log_dir = hermes_root / "logs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "hermes.log"
    log_file.write_text("hello\n", encoding="utf-8")
    roots_path.write_text(json.dumps({
        "hermes_roots": [{"user_hash": "istale", "path": str(hermes_root)}]
    }), encoding="utf-8")

    config = load_roots_config(roots_path)
    paths = paths_for_source(config, source="hermes", user_hash="istale")

    assert paths == [log_file]


def test_imported_event_appears_in_analysis_bundle_timeline(tmp_path, temp_data_dir):
    from app.analysis_bundle import build_analysis_bundle

    log_path = tmp_path / "hermes.log"
    log_path.write_text('{"event_type":"routing_decision","timestamp":"2026-05-31T10:05:00Z","session_id":"session_123","agent_id":"hermes"}\n', encoding="utf-8")
    repo = Repository.from_env()
    repo.upsert_run({
        "run_id": "run_existing",
        "trace_id": "trace_existing",
        "user_hash": "istale",
        "agent_id": "hermes",
        "session_id": "session_123",
        "channel": "discord",
        "started_at": "2026-05-31T10:00:00Z",
        "ended_at": "2026-05-31T10:06:00Z",
        "status": "ok",
    })

    run_import(source="hermes", paths=[log_path], user_hash="istale", repo=repo)

    bundle = build_analysis_bundle("trace_existing", repo=repo)
    assert bundle is not None
    assert [event["event_type"] for event in bundle["timeline"]] == ["routing_decision"]
