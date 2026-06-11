from datetime import datetime, timedelta, timezone

from app.storage.repositories import Repository


def _iso_days_ago(days: float) -> str:
    """Return an ISO-8601 UTC timestamp ``days`` days before now.

    Used so date-window assertions (e.g. ``?days=7``) stay valid as the
    real clock advances instead of going stale on a fixed calendar date.
    """
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _insert_run(repo: Repository, *, trace_id: str, run_id: str, user_hash: str, agent_id: str, channel: str, started_at: str, status: str = "ok") -> None:
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


def _insert_llm_call(repo: Repository, *, trace_id: str, run_id: str, user_hash: str, agent_id: str, channel: str, started_at: str, total_tokens: int, latency_ms: int, suffix: str = "1") -> None:
    repo.insert_llm_call({
        "llm_call_id": f"llm_{trace_id}_{suffix}",
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
        "identity_source": "ingress_route",
    })


def test_subject_users_lists_observed_users_with_counts(app_client):
    repo = Repository.from_env()
    _insert_run(repo, trace_id="trace_istale_1", run_id="run_istale_1", user_hash="istale", agent_id="hermes", channel="discord", started_at="2026-05-30T10:00:00Z")
    _insert_run(repo, trace_id="trace_istale_2", run_id="run_istale_2", user_hash="istale", agent_id="openclaw", channel="desktop", started_at="2026-05-31T10:00:00Z")
    _insert_run(repo, trace_id="trace_alice_1", run_id="run_alice_1", user_hash="alice", agent_id="hermes", channel="discord", started_at="2026-05-31T11:00:00Z")

    response = app_client.get("/api/subjects/users")

    assert response.status_code == 200
    users = {item["user_hash"]: item for item in response.json()["users"]}
    assert users["alice"]["trace_count"] == 1
    assert users["alice"]["agent_count"] == 1
    assert users["istale"]["trace_count"] == 2
    assert users["istale"]["agent_count"] == 2
    assert users["istale"]["channels"] == ["desktop", "discord"]
    assert users["istale"]["first_seen"] == "2026-05-30T10:00:00Z"
    assert users["istale"]["last_seen"] == "2026-05-31T10:00:00Z"


def test_subject_user_traces_returns_recent_traces_with_llm_rollups(app_client):
    repo = Repository.from_env()
    _insert_run(repo, trace_id="trace_old", run_id="run_old", user_hash="istale", agent_id="hermes", channel="discord", started_at="2026-05-29T10:00:00Z")
    _insert_run(repo, trace_id="trace_new", run_id="run_new", user_hash="istale", agent_id="hermes", channel="discord", started_at="2026-05-31T10:00:00Z")
    _insert_run(repo, trace_id="trace_other", run_id="run_other", user_hash="alice", agent_id="hermes", channel="discord", started_at="2026-05-31T11:00:00Z")
    _insert_llm_call(repo, trace_id="trace_new", run_id="run_new", user_hash="istale", agent_id="hermes", channel="discord", started_at="2026-05-31T10:00:00Z", total_tokens=123, latency_ms=456, suffix="1")
    _insert_llm_call(repo, trace_id="trace_new", run_id="run_new", user_hash="istale", agent_id="hermes", channel="discord", started_at="2026-05-31T10:00:01Z", total_tokens=10, latency_ms=900, suffix="2")

    response = app_client.get("/api/subjects/users/istale/traces?limit=1")

    assert response.status_code == 200
    body = response.json()
    assert body["user_hash"] == "istale"
    assert body["filters"] == {"limit": 1, "days": None, "agent_id": None, "channel": None, "status": None}
    assert [item["trace_id"] for item in body["traces"]] == ["trace_new"]
    assert body["traces"][0]["llm_call_count"] == 2
    assert body["traces"][0]["total_tokens"] == 133
    assert body["traces"][0]["max_latency_ms"] == 900


def test_subject_user_traces_filters_by_agent_channel_status_and_days(app_client):
    repo = Repository.from_env()
    # Dates are relative to "now" so the ``?days=7`` window assertion below
    # stays valid as the real clock advances. ``recent`` is well inside the
    # window; ``too_old`` is well outside.
    recent = _iso_days_ago(1)
    too_old = _iso_days_ago(14)
    _insert_run(repo, trace_id="trace_keep", run_id="run_keep", user_hash="istale", agent_id="hermes", channel="discord", started_at=recent, status="ok")
    _insert_run(repo, trace_id="trace_wrong_agent", run_id="run_wrong_agent", user_hash="istale", agent_id="openclaw", channel="discord", started_at=recent, status="ok")
    _insert_run(repo, trace_id="trace_wrong_channel", run_id="run_wrong_channel", user_hash="istale", agent_id="hermes", channel="desktop", started_at=recent, status="ok")
    _insert_run(repo, trace_id="trace_wrong_status", run_id="run_wrong_status", user_hash="istale", agent_id="hermes", channel="discord", started_at=recent, status="error")
    _insert_run(repo, trace_id="trace_too_old", run_id="run_too_old", user_hash="istale", agent_id="hermes", channel="discord", started_at=too_old, status="ok")

    response = app_client.get("/api/subjects/users/istale/traces?agent_id=hermes&channel=discord&status=ok&days=7")

    assert response.status_code == 200
    assert [item["trace_id"] for item in response.json()["traces"]] == ["trace_keep"]


def test_subject_user_agents_lists_agent_channel_combinations(app_client):
    repo = Repository.from_env()
    _insert_run(repo, trace_id="trace_1", run_id="run_1", user_hash="istale", agent_id="hermes", channel="discord", started_at="2026-05-30T10:00:00Z")
    _insert_run(repo, trace_id="trace_2", run_id="run_2", user_hash="istale", agent_id="hermes", channel="discord", started_at="2026-05-31T10:00:00Z")
    _insert_run(repo, trace_id="trace_3", run_id="run_3", user_hash="istale", agent_id="openclaw", channel="desktop", started_at="2026-05-31T11:00:00Z")

    response = app_client.get("/api/subjects/users/istale/agents")

    assert response.status_code == 200
    agents = response.json()["agents"]
    assert agents == [
        {"agent_id": "openclaw", "channel": "desktop", "trace_count": 1, "last_seen": "2026-05-31T11:00:00Z"},
        {"agent_id": "hermes", "channel": "discord", "trace_count": 2, "last_seen": "2026-05-31T10:00:00Z"},
    ]
