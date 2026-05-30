import sqlite3

import httpx
import respx

from app.storage.db import init_db
from app.storage.repositories import Repository


def test_ingress_routes_migration_is_idempotent(temp_data_dir):
    db_path = temp_data_dir / "hub.sqlite3"

    init_db(db_path)
    init_db(db_path)

    with sqlite3.connect(db_path) as conn:
        route_table = conn.execute("select name from sqlite_master where type='table' and name='ingress_routes'").fetchone()
        trace_columns = [row[1] for row in conn.execute("pragma table_info(trace_runs)").fetchall()]
        call_columns = [row[1] for row in conn.execute("pragma table_info(llm_calls)").fetchall()]

    assert route_table is not None
    assert "identity_source" in trace_columns
    assert "identity_source" in call_columns


@respx.mock
def test_ingress_route_fills_missing_identity_fields(app_client):
    repo = Repository.from_env()
    repo.insert_ingress_route({
        "listen_host": "127.0.0.1",
        "listen_port": 43180,
        "path_prefix": "/v1",
        "tenant_id": "local",
        "user_hash": "istale",
        "agent_id": "hermes",
        "channel": "discord",
        "note": "main Hermes gateway",
    })
    respx.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    )

    response = app_client.post(
        "http://127.0.0.1:43180/v1/chat/completions",
        headers={"X-Trace-Id": "trace_route_fill", "X-Run-Id": "run_route_fill"},
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    run = app_client.get("/api/runs/run_route_fill").json()["run"]
    call = app_client.get("/api/traces/trace_route_fill/llm-calls").json()["llm_calls"][0]
    correlations = app_client.get("/api/traces/trace_route_fill/correlations").json()["correlations"]
    pairs = {(item["source"], item["key"], item["value"]) for item in correlations}

    assert run["agent_id"] == "hermes"
    assert run["channel"] == "discord"
    assert run["user_hash"] == "istale"
    assert run["identity_source"] == "ingress_route"
    assert call["identity_source"] == "ingress_route"
    assert ("ingress_route", "agent_id", "hermes") in pairs
    assert ("ingress_route", "channel", "discord") in pairs
    assert ("ingress_route", "user_hash", "istale") in pairs


@respx.mock
def test_headers_win_over_ingress_route_defaults(app_client):
    repo = Repository.from_env()
    repo.insert_ingress_route({
        "listen_host": "127.0.0.1",
        "listen_port": 43180,
        "path_prefix": "/v1",
        "agent_id": "hermes",
        "channel": "discord",
    })
    respx.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    )

    response = app_client.post(
        "http://127.0.0.1:43180/v1/chat/completions",
        headers={
            "X-Trace-Id": "trace_header_wins",
            "X-Run-Id": "run_header_wins",
            "X-Agent-Id": "openclaw",
            "X-Channel": "cli",
        },
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    run = app_client.get("/api/runs/run_header_wins").json()["run"]
    assert run["agent_id"] == "openclaw"
    assert run["channel"] == "cli"
    assert run["identity_source"] == "headers"


@respx.mock
def test_ingress_route_mixed_with_header_session(app_client):
    repo = Repository.from_env()
    repo.insert_ingress_route({
        "listen_host": "127.0.0.1",
        "listen_port": 43180,
        "path_prefix": "/v1",
        "agent_id": "hermes",
        "channel": "discord",
    })
    respx.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    )

    response = app_client.post(
        "http://127.0.0.1:43180/v1/chat/completions",
        headers={
            "X-Trace-Id": "trace_mixed",
            "X-Run-Id": "run_mixed",
            "X-Session-Id": "hermes-session-123",
        },
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    run = app_client.get("/api/runs/run_mixed").json()["run"]
    assert run["agent_id"] == "hermes"
    assert run["channel"] == "discord"
    assert run["session_id"] == "hermes-session-123"
    assert run["identity_source"] == "mixed"


@respx.mock
def test_disabled_ingress_route_is_ignored(app_client):
    repo = Repository.from_env()
    repo.insert_ingress_route({
        "listen_host": "127.0.0.1",
        "listen_port": 43180,
        "path_prefix": "/v1",
        "agent_id": "hermes",
        "channel": "discord",
        "enabled": 0,
    })
    respx.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    )

    response = app_client.post(
        "http://127.0.0.1:43180/v1/chat/completions",
        headers={"X-Trace-Id": "trace_disabled", "X-Run-Id": "run_disabled"},
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    run = app_client.get("/api/runs/run_disabled").json()["run"]
    assert run["agent_id"] == "unknown"
    assert run["channel"] == "unknown"
    assert run["identity_source"] == "unknown"
