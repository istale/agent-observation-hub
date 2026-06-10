"""Tests for the (user_id, chat_id) overlay surface used by pi-adapter."""
from __future__ import annotations

import json

from app.config import get_settings


def _snap_path(user_id: str, chat_id: str):
    return get_settings().observation_dir / "overlays" / "chats" / user_id / f"{chat_id}.json"


def test_mark_writes_snapshot_under_user_subdir(app_client):
    r = app_client.post("/api/chats/alice/chat-1/messages/0/mark", json={"mark": "stale"})
    assert r.status_code == 200
    path = _snap_path("alice", "chat-1")
    assert path.exists()
    body = json.loads(path.read_text())
    assert body["user_id"] == "alice"
    assert body["chat_id"] == "chat-1"
    assert body["overlays"][0]["mark"] == "stale"


def test_isolation_per_user(app_client):
    app_client.post("/api/chats/alice/c/messages/0/mark", json={"mark": "stale"})
    app_client.post("/api/chats/bob/c/messages/0/mark", json={"mark": "hidden"})
    a = json.loads(_snap_path("alice", "c").read_text())
    b = json.loads(_snap_path("bob", "c").read_text())
    assert a["overlays"][0]["mark"] == "stale"
    assert b["overlays"][0]["mark"] == "hidden"


def test_reverting_to_active_deletes_snapshot(app_client):
    app_client.post("/api/chats/alice/c2/messages/0/mark", json={"mark": "stale"})
    assert _snap_path("alice", "c2").exists()
    app_client.post("/api/chats/alice/c2/messages/0/mark", json={"mark": "active"})
    assert not _snap_path("alice", "c2").exists()


def test_invalid_mark_returns_400(app_client):
    r = app_client.post("/api/chats/alice/c/messages/0/mark", json={"mark": "wrong"})
    assert r.status_code == 400


def test_note_round_trip(app_client):
    app_client.post("/api/chats/alice/c3/messages/0/mark", json={"mark": "background"})
    app_client.post("/api/chats/alice/c3/messages/0/note", json={"note": "this is context"})
    body = json.loads(_snap_path("alice", "c3").read_text())
    assert body["overlays"][0]["note"] == "this is context"


def test_blank_note_clears(app_client):
    app_client.post("/api/chats/alice/c4/messages/0/mark", json={"mark": "background"})
    app_client.post("/api/chats/alice/c4/messages/0/note", json={"note": "x"})
    app_client.post("/api/chats/alice/c4/messages/0/note", json={"note": "   "})
    body = json.loads(_snap_path("alice", "c4").read_text())
    assert body["overlays"][0]["note"] is None


def test_path_traversal_rejected(app_client):
    r = app_client.post("/api/chats/..%2Fbad/c/messages/0/mark", json={"mark": "stale"})
    # The path component reaches the handler URL-decoded; either FastAPI 404 or 400 from our validator is acceptable.
    assert r.status_code in (400, 404)


def test_overlay_get_lists_rows(app_client):
    app_client.post("/api/chats/alice/c5/messages/0/mark", json={"mark": "stale"})
    app_client.post("/api/chats/alice/c5/messages/2/mark", json={"mark": "hidden"})
    body = app_client.get("/api/chats/alice/c5/overlay").json()
    indices = {ov["index"] for ov in body["overlays"]}
    assert indices == {0, 2}
    assert body["snapshot_present"] is True
