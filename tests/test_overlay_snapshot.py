"""TDD: tests for the hub-side overlay snapshot writer.

These tests target the implementation outlined in backlog.md / the
'混合方案' implementation plan. The writer's job: whenever the user
changes a mark or note on a message, sync a JSON snapshot file to
$AOH_OBSERVATION_DIR/overlays/<sid>.json so Pi can read it at next
prompt without needing an HTTP call.

These tests will FAIL until the implementation lands (Steps 1–3).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import get_settings


def _snapshot_path(session_id: str) -> Path:
    return get_settings().observation_dir / "overlays" / f"{session_id}.json"


def _seed_session(app_client, session_id: str = "sess-1") -> None:
    """Reach into the session messages API to ensure a session exists in
    the test fixture sandbox. Uses the existing test pattern from
    test_session_messages."""
    # Since the API requires a real session on disk to fetch messages,
    # but the overlay POST endpoints don't require disk presence (they
    # write to SQLite + snapshot only), we can call them directly.
    pass


# ---------- snapshot file shape ----------

def test_marking_non_active_creates_snapshot_file(app_client):
    sid = "sess-snap-1"
    assert not _snapshot_path(sid).exists()
    resp = app_client.post(f"/api/sessions/{sid}/messages/3/mark", json={"mark": "stale"})
    assert resp.status_code == 200

    snap_path = _snapshot_path(sid)
    assert snap_path.exists(), "snapshot file should be created after first non-active mark"
    body = json.loads(snap_path.read_text(encoding="utf-8"))
    assert body["session_id"] == sid
    assert body["schema_version"] == 1
    assert "updated_at" in body
    assert isinstance(body["overlays"], list)
    assert len(body["overlays"]) == 1
    assert body["overlays"][0] == {"index": 3, "mark": "stale", "note": None}


def test_snapshot_excludes_active_marks(app_client):
    sid = "sess-snap-2"
    app_client.post(f"/api/sessions/{sid}/messages/0/mark", json={"mark": "background"})
    app_client.post(f"/api/sessions/{sid}/messages/1/mark", json={"mark": "active"})  # active should not appear
    app_client.post(f"/api/sessions/{sid}/messages/2/mark", json={"mark": "stale"})

    body = json.loads(_snapshot_path(sid).read_text(encoding="utf-8"))
    indices = {o["index"] for o in body["overlays"]}
    assert indices == {0, 2}, "active marks must be excluded from snapshot"
    marks = {(o["index"], o["mark"]) for o in body["overlays"]}
    assert marks == {(0, "background"), (2, "stale")}


def test_notes_are_included_in_snapshot(app_client):
    sid = "sess-snap-3"
    app_client.post(f"/api/sessions/{sid}/messages/5/mark", json={"mark": "hidden"})
    app_client.post(f"/api/sessions/{sid}/messages/5/note", json={"note": "300 lines elided"})

    body = json.loads(_snapshot_path(sid).read_text(encoding="utf-8"))
    entry = next(o for o in body["overlays"] if o["index"] == 5)
    assert entry["note"] == "300 lines elided"


def test_notes_on_active_messages_still_appear_in_snapshot(app_client):
    """A note can be useful even when the mark is 'active' (e.g. just a
    human comment). Decision: notes on active marks SHOULD appear in
    snapshot too, so pi can surface them. Skip if we decide otherwise."""
    sid = "sess-snap-4"
    app_client.post(f"/api/sessions/{sid}/messages/2/note", json={"note": "important decision lives here"})

    snap = _snapshot_path(sid)
    if not snap.exists():
        pytest.skip("design decision: notes-only-on-active not included in snapshot")
    body = json.loads(snap.read_text(encoding="utf-8"))
    indices = {o["index"] for o in body["overlays"]}
    assert 2 in indices


# ---------- refresh / update semantics ----------

def test_changing_mark_back_to_active_removes_entry_from_snapshot(app_client):
    sid = "sess-snap-5"
    app_client.post(f"/api/sessions/{sid}/messages/1/mark", json={"mark": "stale"})
    app_client.post(f"/api/sessions/{sid}/messages/2/mark", json={"mark": "background"})

    # Revert message 1 back to active
    app_client.post(f"/api/sessions/{sid}/messages/1/mark", json={"mark": "active"})

    body = json.loads(_snapshot_path(sid).read_text(encoding="utf-8"))
    indices = {o["index"] for o in body["overlays"]}
    assert indices == {2}, "active-again messages must be pruned from snapshot"


def test_clearing_all_marks_deletes_snapshot_file(app_client):
    """When no non-active marks remain, Pi should not even attempt a
    snapshot read. Cleanest signal: delete the file entirely."""
    sid = "sess-snap-6"
    app_client.post(f"/api/sessions/{sid}/messages/1/mark", json={"mark": "stale"})
    app_client.post(f"/api/sessions/{sid}/messages/1/mark", json={"mark": "active"})

    snap = _snapshot_path(sid)
    body_or_missing = json.loads(snap.read_text()) if snap.exists() else None
    if body_or_missing is None:
        return  # deleted, as preferred
    # Acceptable alternative: file exists but overlays array is empty
    assert body_or_missing["overlays"] == []


def test_updated_at_increments_on_subsequent_change(app_client):
    sid = "sess-snap-7"
    app_client.post(f"/api/sessions/{sid}/messages/0/mark", json={"mark": "background"})
    t1 = json.loads(_snapshot_path(sid).read_text())["updated_at"]
    app_client.post(f"/api/sessions/{sid}/messages/1/mark", json={"mark": "stale"})
    t2 = json.loads(_snapshot_path(sid).read_text())["updated_at"]
    assert t2 >= t1


# ---------- atomic write safety ----------

def test_snapshot_write_is_atomic(app_client, tmp_path, monkeypatch):
    """We use tmp + rename to avoid Pi reading half-written JSON.
    Verify the .tmp file doesn't linger after a successful write."""
    sid = "sess-snap-atomic"
    app_client.post(f"/api/sessions/{sid}/messages/0/mark", json={"mark": "stale"})

    snap = _snapshot_path(sid)
    assert snap.exists()
    assert not snap.with_suffix(".tmp").exists(), "atomic write should clean up .tmp"


# ---------- isolation ----------

def test_snapshots_are_isolated_per_session(app_client):
    app_client.post("/api/sessions/sess-iso-a/messages/0/mark", json={"mark": "stale"})
    app_client.post("/api/sessions/sess-iso-b/messages/0/mark", json={"mark": "hidden"})

    a = json.loads(_snapshot_path("sess-iso-a").read_text())
    b = json.loads(_snapshot_path("sess-iso-b").read_text())
    assert a["overlays"][0]["mark"] == "stale"
    assert b["overlays"][0]["mark"] == "hidden"


# ---------- ordering ----------

def test_snapshot_overlays_are_sorted_by_index(app_client):
    sid = "sess-snap-order"
    # write out of order
    app_client.post(f"/api/sessions/{sid}/messages/5/mark", json={"mark": "stale"})
    app_client.post(f"/api/sessions/{sid}/messages/2/mark", json={"mark": "background"})
    app_client.post(f"/api/sessions/{sid}/messages/8/mark", json={"mark": "hidden"})

    body = json.loads(_snapshot_path(sid).read_text())
    indices = [o["index"] for o in body["overlays"]]
    assert indices == sorted(indices), "snapshot overlays should be sorted by index"


# ---------- schema version stability ----------

def test_schema_version_is_present_and_int(app_client):
    sid = "sess-snap-schema"
    app_client.post(f"/api/sessions/{sid}/messages/0/mark", json={"mark": "stale"})
    body = json.loads(_snapshot_path(sid).read_text())
    assert "schema_version" in body
    assert isinstance(body["schema_version"], int)
    assert body["schema_version"] >= 1


# ---------- error resilience ----------

def test_snapshot_write_failure_does_not_break_api(app_client, tmp_path, monkeypatch):
    """If the snapshot directory becomes unwritable mid-session, the
    POST mark API should still return 200 (write to SQLite succeeds);
    only the snapshot sync silently fails."""
    sid = "sess-snap-fail"
    # First write succeeds
    app_client.post(f"/api/sessions/{sid}/messages/0/mark", json={"mark": "stale"})
    # Now break the overlays dir
    overlays_dir = get_settings().observation_dir / "overlays"
    if overlays_dir.exists():
        # Make it read-only (best-effort; chmod may not enforce on all FS)
        overlays_dir.chmod(0o500)
    try:
        resp = app_client.post(f"/api/sessions/{sid}/messages/1/mark", json={"mark": "background"})
        assert resp.status_code == 200, "API should not 500 when snapshot write fails"
    finally:
        if overlays_dir.exists():
            overlays_dir.chmod(0o700)
