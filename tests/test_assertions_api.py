"""Tests for /api/assertions/* — the AI-runnable regression surface."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _post_event(client, trace_id, session_id, stage, payload, ts=None):
    """Simulate the tailer ingesting an agent event into the hub DB."""
    body = {
        "trace_id": trace_id,
        "session_id": session_id,
        "event_seq": 1,
        "stage": stage,
        "payload": payload,
    }
    if ts:
        body["ts"] = ts
    return client.post("/api/agent-events", json=body)


# ---------- /api/assertions/overlay/{sid} ----------

def test_assertions_overlay_empty_when_no_marks(app_client):
    r = app_client.get("/api/assertions/overlay/sid-fresh")
    assert r.status_code == 200
    body = r.json()
    assert body["db"]["all_count"] == 0
    assert body["db"]["non_active_count"] == 0
    assert body["snapshot"]["exists"] is False
    assert body["consistent"] is True


def test_assertions_overlay_reports_snapshot_after_mark(app_client):
    app_client.post("/api/sessions/sid-a/messages/0/mark", json={"mark": "stale"})
    body = app_client.get("/api/assertions/overlay/sid-a").json()
    assert body["snapshot"]["exists"] is True
    assert body["snapshot"]["content"]["overlays"][0]["mark"] == "stale"
    assert body["db"]["non_active_count"] == 1
    assert body["consistent"] is True


def test_assertions_overlay_detects_inconsistency(app_client):
    """If DB has non-active rows but snapshot is missing, consistent=False."""
    app_client.post("/api/sessions/sid-b/messages/0/mark", json={"mark": "background"})
    from app.config import get_settings
    snap = get_settings().observation_dir / "overlays" / "sid-b.json"
    snap.unlink()
    body = app_client.get("/api/assertions/overlay/sid-b").json()
    assert body["snapshot"]["exists"] is False
    assert body["db"]["non_active_count"] == 1
    assert body["consistent"] is False


def test_assertions_overlay_detects_triple_drift(app_client):
    """Length matches but a triple differs → consistent=False + drift listed.

    Simulates the bug where AI agent regression would have falsely PASSed:
    DB says (0, "stale", None) but snapshot writer kept stale (0, "background", None).
    """
    import json
    from app.config import get_settings
    app_client.post("/api/sessions/sid-drift/messages/0/mark", json={"mark": "stale"})
    snap = get_settings().observation_dir / "overlays" / "sid-drift.json"
    body = json.loads(snap.read_text())
    body["overlays"][0]["mark"] = "background"  # tamper to simulate drift
    snap.write_text(json.dumps(body))

    resp = app_client.get("/api/assertions/overlay/sid-drift").json()
    assert resp["consistent"] is False
    sides = {(d["side"], d["mark"]) for d in resp["drift"]}
    assert ("db_only", "stale") in sides
    assert ("snapshot_only", "background") in sides


# ---------- /api/assertions/overlay-applied/{sid} ----------

def test_assertions_overlay_applied_lists_events(app_client):
    _post_event(app_client, "trace-x1", "sid-c", "overlay_applied", {
        "overlay_count": 2, "stale_count": 1, "hidden_count": 1,
        "applied_indices": [0, 1], "annotation_chars": 250,
    }, ts="2026-06-09T02:00:00Z")
    body = app_client.get("/api/assertions/overlay-applied/sid-c").json()
    assert body["count"] == 1
    assert body["events"][0]["trace_id"] == "trace-x1"
    assert body["events"][0]["payload"]["stale_count"] == 1


def test_assertions_overlay_applied_filters_by_since(app_client):
    _post_event(app_client, "old-trace", "sid-d", "overlay_applied", {"overlay_count": 1}, ts="2026-06-08T00:00:00Z")
    _post_event(app_client, "new-trace", "sid-d", "overlay_applied", {"overlay_count": 1}, ts="2026-06-09T12:00:00Z")
    body = app_client.get("/api/assertions/overlay-applied/sid-d?since=2026-06-09T00:00:00Z").json()
    assert body["count"] == 1
    assert body["events"][0]["trace_id"] == "new-trace"


# ---------- /api/assertions/payload-inspect/{tid} ----------

def test_payload_inspect_404_when_no_payload(app_client):
    r = app_client.get("/api/assertions/payload-inspect/no-such-trace")
    assert r.status_code == 404


def test_payload_inspect_detects_annotation(app_client):
    _post_event(app_client, "trace-anno", "sid-e", "before_provider_payload", {
        "model": {"id": "m"},
        "payload": {
            "messages": [
                {"role": "system", "content": "You are helpful.\n\n---\n\nThe user has annotated this conversation.\nSTALE — overruled:\n  - turn 1"},
                {"role": "user", "content": "hi"},
            ],
        },
    })
    body = app_client.get("/api/assertions/payload-inspect/trace-anno").json()
    assert body["annotation_in_system_prompt"] is True
    assert "STALE" in body["annotation_mentions"]
    assert body["payload_message_count"] == 2


def test_payload_inspect_detects_tombstone_and_pairing(app_client):
    _post_event(app_client, "trace-tomb", "sid-f", "before_provider_payload", {
        "model": {"id": "m"},
        "payload": {
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": "y"},
                {"role": "tool", "tool_call_id": "abc", "content": "[content elided by user; see annotation in system prompt for context]"},
            ],
        },
    })
    body = app_client.get("/api/assertions/payload-inspect/trace-tomb").json()
    assert body["tombstoned_count"] == 1
    assert body["tombstoned"][0]["role"] == "tool"
    assert body["tombstoned"][0]["tool_call_id"] == "abc"
    assert body["tombstoned"][0]["pairing_intact"] is True
    assert body["tool_pairing_intact"] is True


def test_payload_inspect_flags_broken_pairing(app_client):
    _post_event(app_client, "trace-broken", "sid-g", "before_provider_payload", {
        "model": {"id": "m"},
        "payload": {
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "tool", "content": "[content elided by user; see annotation in system prompt]"},
            ],
        },
    })
    body = app_client.get("/api/assertions/payload-inspect/trace-broken").json()
    assert body["tool_pairing_intact"] is False
    assert "missing tool_call_id" in body["pairing_issues"][0]


# ---------- /api/assertions/session-summary/{sid} ----------

def test_session_summary_composite(app_client):
    app_client.post("/api/sessions/sid-h/messages/0/mark", json={"mark": "stale"})
    _post_event(app_client, "tracex", "sid-h", "before_provider_payload", {
        "model": {"id": "m"},
        "payload": {
            "messages": [
                {"role": "system", "content": "...STALE — overruled:\n  - turn 0"},
                {"role": "user", "content": "hi"},
            ],
        },
    }, ts="2026-06-09T10:00:00Z")
    _post_event(app_client, "tracex", "sid-h", "overlay_applied", {
        "overlay_count": 1, "stale_count": 1, "applied_indices": [0],
    }, ts="2026-06-09T10:00:01Z")
    body = app_client.get("/api/assertions/session-summary/sid-h").json()
    assert body["overlay"]["snapshot"]["exists"] is True
    assert body["model_call_count"] == 1
    mc = body["model_calls"][0]
    assert mc["overlay_applied"]["fired"] is True
    assert mc["overlay_applied"]["stale_count"] == 1
    assert mc["payload_inspection"]["annotation_in_system_prompt"] is True
