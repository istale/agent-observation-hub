"""Functional tests for the Memory Editing UI API + reader + repo."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.pi_session_reader import (
    find_session_file,
    invalidate_cache,
    list_known_sessions,
    read_messages,
    session_metadata,
)
from app.storage.repositories import Repository


@pytest.fixture()
def sample_sessions_dir(tmp_path: Path, monkeypatch):
    """Create a fake ~/.pi/agent/sessions layout with two sessions."""
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    monkeypatch.setenv("AOH_PI_SESSIONS_DIR", str(sessions_root))
    invalidate_cache()

    def write(sub: str, name: str, entries: list[dict]):
        sub_dir = sessions_root / sub
        sub_dir.mkdir(parents=True, exist_ok=True)
        path = sub_dir / name
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
        return path

    write(
        "--Users-test-proj-A--",
        "2026-01-01T00-00-00-000Z_aaa.jsonl",
        [
            {"type": "session", "id": "sess-aaa", "timestamp": "2026-01-01T00:00:00Z", "cwd": "/Users/test/proj/A"},
            {"type": "message", "id": "e1", "message": {"role": "user", "content": "hello"}},
            {"type": "message", "id": "e2", "parentId": "e1", "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}, {"type": "thinking", "text": "thinking..."}]}},
            {"type": "message", "id": "e3", "parentId": "e2", "message": {"role": "toolResult", "toolName": "bash", "toolCallId": "tc1", "content": "ok"}},
        ],
    )
    write(
        "--Users-test-proj-B--",
        "2026-02-02T00-00-00-000Z_bbb.jsonl",
        [
            {"type": "session", "id": "sess-bbb", "timestamp": "2026-02-02T00:00:00Z", "cwd": "/Users/test/proj/B"},
            {"type": "message", "id": "f1", "message": {"role": "user", "content": "only one"}},
        ],
    )
    yield sessions_root
    invalidate_cache()


def test_reader_finds_session_metadata(sample_sessions_dir):
    meta = session_metadata("sess-aaa")
    assert meta is not None
    assert meta["session_id"] == "sess-aaa"
    assert meta["cwd"] == "/Users/test/proj/A"
    assert meta["jsonl_path"].endswith("aaa.jsonl")


def test_reader_lists_all_sessions(sample_sessions_dir):
    sessions = list_known_sessions()
    ids = {s.session_id for s in sessions}
    assert ids == {"sess-aaa", "sess-bbb"}


def test_reader_returns_none_for_unknown_session(sample_sessions_dir):
    assert session_metadata("does-not-exist") is None
    assert read_messages("does-not-exist") is None


def test_reader_extracts_message_fields(sample_sessions_dir):
    msgs = read_messages("sess-aaa")
    assert msgs is not None
    assert len(msgs) == 3
    assert msgs[0]["role"] == "user"
    assert msgs[0]["text"] == "hello"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["has_thinking"] is True
    assert msgs[2]["role"] == "toolResult"
    assert msgs[2]["tool_name"] == "bash"
    assert msgs[2]["tool_call_id"] == "tc1"
    # indices are sequential
    assert [m["index"] for m in msgs] == [0, 1, 2]


def test_api_get_messages_returns_404_for_unknown(app_client, sample_sessions_dir):
    resp = app_client.get("/api/sessions/does-not-exist/messages")
    assert resp.status_code == 404


def test_api_get_messages_returns_data(app_client, sample_sessions_dir):
    resp = app_client.get("/api/sessions/sess-aaa/messages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["cwd"] == "/Users/test/proj/A"
    assert len(data["messages"]) == 3
    # all default to active mark with no note
    for m in data["messages"]:
        assert m["mark"] == "active"
        assert m["note"] is None


def test_set_mark_then_persists_in_get(app_client, sample_sessions_dir):
    r = app_client.post("/api/sessions/sess-aaa/messages/1/mark", json={"mark": "background"})
    assert r.status_code == 200
    assert r.json()["overlay"]["mark"] == "background"

    data = app_client.get("/api/sessions/sess-aaa/messages").json()
    assert data["messages"][1]["mark"] == "background"
    assert data["messages"][0]["mark"] == "active"  # others unchanged


def test_set_note_independently_of_mark(app_client, sample_sessions_dir):
    app_client.post("/api/sessions/sess-aaa/messages/0/note", json={"note": "this kicked everything off"})
    data = app_client.get("/api/sessions/sess-aaa/messages").json()
    assert data["messages"][0]["mark"] == "active"  # mark left default
    assert data["messages"][0]["note"] == "this kicked everything off"


def test_set_mark_then_note_keeps_both(app_client, sample_sessions_dir):
    app_client.post("/api/sessions/sess-aaa/messages/2/mark", json={"mark": "stale"})
    app_client.post("/api/sessions/sess-aaa/messages/2/note", json={"note": "tool result was misleading"})
    data = app_client.get("/api/sessions/sess-aaa/messages").json()
    assert data["messages"][2]["mark"] == "stale"
    assert data["messages"][2]["note"] == "tool result was misleading"


def test_invalid_mark_rejected(app_client, sample_sessions_dir):
    r = app_client.post("/api/sessions/sess-aaa/messages/0/mark", json={"mark": "deleted"})
    assert r.status_code == 400


def test_empty_note_clears_it(app_client, sample_sessions_dir):
    app_client.post("/api/sessions/sess-aaa/messages/0/note", json={"note": "first"})
    app_client.post("/api/sessions/sess-aaa/messages/0/note", json={"note": "   "})
    data = app_client.get("/api/sessions/sess-aaa/messages").json()
    assert data["messages"][0]["note"] is None


def test_overlays_are_isolated_per_session(app_client, sample_sessions_dir):
    app_client.post("/api/sessions/sess-aaa/messages/0/mark", json={"mark": "hidden"})
    data_b = app_client.get("/api/sessions/sess-bbb/messages").json()
    assert data_b["messages"][0]["mark"] == "active"


def test_repo_list_overlays_returns_indexed_map(app_client, sample_sessions_dir):
    app_client.post("/api/sessions/sess-aaa/messages/0/mark", json={"mark": "hidden"})
    app_client.post("/api/sessions/sess-aaa/messages/2/mark", json={"mark": "stale"})
    overlays = Repository.from_env().list_message_overlays("sess-aaa")
    assert set(overlays.keys()) == {0, 2}
    assert overlays[0]["mark"] == "hidden"
    assert overlays[2]["mark"] == "stale"
