"""Functional tests for agent_events: ingestion API, repository queries, view shapers, tailer."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.agent_event_views import enrich_events
from app.config import get_settings
from app.observation_tailer import _scan_once
from app.storage.repositories import Repository


def _post(client, payload):
    return client.post("/api/agent-events", json=payload)


def test_post_small_payload_stored_inline(app_client):
    resp = _post(app_client, {
        "trace_id": "trace-aa",
        "session_id": "sess-1",
        "event_seq": 1,
        "stage": "before_provider_request",
        "source_module": "test",
        "ts": "2026-06-06T00:00:00Z",
        "payload": {"hello": "world"},
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True

    get_resp = app_client.get("/api/traces/trace-aa/agent-events")
    events = get_resp.json()["agent_events"]
    assert len(events) == 1
    ev = events[0]
    assert ev["stage"] == "before_provider_request"
    assert ev["payload_ref"] is None
    assert json.loads(ev["payload_inline"]) == {"hello": "world"}


def test_post_large_payload_written_to_ref(app_client):
    big = {"messages": [{"role": "user", "content": "x" * 8000}]}
    resp = _post(app_client, {
        "trace_id": "trace-big",
        "session_id": "sess-1",
        "event_seq": 1,
        "stage": "context",
        "payload": big,
    })
    assert resp.status_code == 200

    events = app_client.get("/api/traces/trace-big/agent-events").json()["agent_events"]
    assert events[0]["payload_inline"] is None
    ref = events[0]["payload_ref"]
    assert ref is not None
    abs_path = get_settings().data_dir / ref
    on_disk = json.loads(abs_path.read_text(encoding="utf-8"))
    assert on_disk["messages"][0]["content"].startswith("x")


def test_session_rollup_across_trace_ids(app_client):
    for tid, stage in [
        ("prompt_x", "before_agent_start"),
        ("session_x_init", "resource_loaded"),
        ("model_x", "context"),
        ("tool_x", "tool_call"),
        ("tool_x", "tool_result"),
    ]:
        _post(app_client, {
            "trace_id": tid,
            "session_id": "sess-xyz",
            "event_seq": 1,
            "stage": stage,
            "payload": {"k": "v"},
        })
    rollup = app_client.get("/api/sessions/sess-xyz/agent-events").json()["agent_events"]
    stages = [e["stage"] for e in rollup]
    assert "before_agent_start" in stages
    assert "resource_loaded" in stages
    assert "context" in stages
    assert stages.count("tool_call") == 1
    assert stages.count("tool_result") == 1


def test_missing_trace_id_rejected(app_client):
    resp = app_client.post("/api/agent-events", json={"stage": "context", "payload": {}})
    assert resp.status_code == 400


def test_stage_counts_for_sessions(app_client):
    for stage, n in [("before_agent_start", 1), ("tool_call", 3), ("tool_result", 3)]:
        for i in range(n):
            _post(app_client, {
                "trace_id": f"t-{stage}-{i}",
                "session_id": "sess-counted",
                "event_seq": i + 1,
                "stage": stage,
                "payload": {},
            })
    repo = Repository.from_env()
    counts = repo.stage_counts_for_sessions(["sess-counted", "sess-missing"])
    assert counts["sess-counted"]["before_agent_start"] == 1
    assert counts["sess-counted"]["tool_call"] == 3
    assert counts["sess-counted"]["tool_result"] == 3
    assert counts["sess-missing"] == {}


@pytest.mark.asyncio
async def test_tailer_ingests_jsonl_file(app_client, tmp_path):
    """Tailer should read newly appended JSONL lines and insert them as agent events."""
    obs_dir = get_settings().observation_dir
    obs_dir.mkdir(parents=True, exist_ok=True)
    f = obs_dir / "trace_tailtest.jsonl"
    f.write_text(json.dumps({
        "trace_id": "tail-1",
        "session_id": "sess-tail",
        "event_seq": 1,
        "stage": "context",
        "source_module": "test",
        "ts": "2026-06-06T00:00:00Z",
        "payload": {"messages": [{"role": "user", "content": "hi"}]},
    }) + "\n")
    state: dict[str, int] = {}
    count = _scan_once(obs_dir, state)
    assert count == 1
    events = app_client.get("/api/traces/tail-1/agent-events").json()["agent_events"]
    assert events[0]["stage"] == "context"

    # Append a 2nd line and confirm only the new one is ingested
    with f.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps({
            "trace_id": "tail-1",
            "session_id": "sess-tail",
            "event_seq": 2,
            "stage": "before_provider_payload",
            "payload": {"any": "thing"},
        }) + "\n")
    count2 = _scan_once(obs_dir, state)
    assert count2 == 1
    events = app_client.get("/api/traces/tail-1/agent-events").json()["agent_events"]
    assert len(events) == 2


def test_tailer_skips_partial_lines(app_client):
    obs_dir = get_settings().observation_dir
    obs_dir.mkdir(parents=True, exist_ok=True)
    f = obs_dir / "trace_partial.jsonl"
    f.write_text(json.dumps({"trace_id": "pt", "stage": "x", "payload": {}}))  # no trailing newline
    state: dict[str, int] = {}
    count = _scan_once(obs_dir, state)
    assert count == 0  # partial line should not ingest


def test_view_shaper_context_produces_message_cards():
    events = [{
        "stage": "context",
        "payload_inline": json.dumps({
            "model": {"id": "m"},
            "messages": [
                {"role": "system", "content": "you are helpful"},
                {"role": "user", "content": [{"type": "text", "text": "hello"}]},
            ],
            "tools": [{"name": "read", "description": "read a file"}],
        }),
        "payload_ref": None,
    }]
    out = enrich_events(events)
    view = out[0]["view"]
    assert view["kind"] == "context"
    assert view["message_count"] == 2
    assert view["messages"][0]["role"] == "system"
    assert view["messages"][1]["role"] == "user"
    assert "hello" in view["messages"][1]["preview"]
    assert view["tools"][0]["name"] == "read"


def test_view_shaper_tool_result_flattens_content_blocks():
    events = [{
        "stage": "tool_result",
        "payload_inline": json.dumps({
            "tool_name": "bash",
            "tool_call_id": "tid",
            "is_error": False,
            "duration_ms": 42,
            "result": [{"type": "text", "text": "stdout line 1"}, {"type": "text", "text": "stdout line 2"}],
        }),
        "payload_ref": None,
    }]
    out = enrich_events(events)
    view = out[0]["view"]
    assert view["kind"] == "tool_result"
    assert view["duration_ms"] == 42
    assert "stdout line 1" in view["result_preview"]
    assert "stdout line 2" in view["result_preview"]


def test_view_shaper_truncation():
    long = "y" * 2000
    events = [{
        "stage": "tool_call",
        "payload_inline": json.dumps({"tool_name": "bash", "tool_call_id": "x", "args": {"cmd": long}}),
        "payload_ref": None,
    }]
    out = enrich_events(events)
    view = out[0]["view"]
    assert view["args_truncated"] is True
    assert len(view["args_preview"]) == 800
    assert view["args_full"].count("y") == 2000
