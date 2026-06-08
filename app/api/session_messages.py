"""Memory Editing UI (MEU): session messages + per-message overlay.

Read-only on Pi's session JSONL. Soft marks + notes are stored in
session_message_overlays so the source-of-truth session file is never
modified.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.pi_session_reader import read_messages, session_metadata
from app.storage.repositories import Repository

router = APIRouter()

VALID_MARKS = {"active", "background", "stale", "hidden"}


def _merged(session_id: str) -> dict[str, Any] | None:
    meta = session_metadata(session_id)
    if meta is None:
        return None
    messages = read_messages(session_id) or []
    overlays = Repository.from_env().list_message_overlays(session_id)
    for m in messages:
        ov = overlays.get(m["index"])
        m["mark"] = ov["mark"] if ov else "active"
        m["note"] = ov["note"] if ov else None
        m["overlay_updated_at"] = ov["updated_at"] if ov else None
    return {"meta": meta, "messages": messages}


@router.get("/api/sessions/{session_id}/messages")
def get_session_messages(session_id: str) -> dict[str, Any]:
    data = _merged(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found on disk")
    return data


@router.post("/api/sessions/{session_id}/messages/{message_index}/mark")
async def set_message_mark(session_id: str, message_index: int, request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc
    mark = (body.get("mark") or "").strip()
    if mark not in VALID_MARKS:
        raise HTTPException(status_code=400, detail=f"mark must be one of {sorted(VALID_MARKS)}")
    row = Repository.from_env().set_message_overlay(session_id, message_index, mark=mark)
    return {"ok": True, "overlay": row}


@router.post("/api/sessions/{session_id}/messages/{message_index}/note")
async def set_message_note(session_id: str, message_index: int, request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc
    if "note" not in body:
        raise HTTPException(status_code=400, detail="body must include a 'note' field (string or null)")
    note = body["note"]
    if note is not None and not isinstance(note, str):
        raise HTTPException(status_code=400, detail="note must be a string or null")
    # Whitespace-only string is treated as "clear" so the UI's empty textarea
    # round-trips correctly.
    if isinstance(note, str) and note.strip() == "":
        note = None
    row = Repository.from_env().set_message_overlay(session_id, message_index, note=note)
    return {"ok": True, "overlay": row}
