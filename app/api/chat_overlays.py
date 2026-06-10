"""Overlay marks keyed by (user_id, chat_id) for the Open WebUI flow.

The pre-existing /api/sessions/* overlay path keys by Pi session_id and
is still used by the Pi TUI workflow. When the agent runtime lives in
pi-adapter, the conversation source of truth is Open WebUI's chat row,
addressed by (user_id, chat_id). This module exposes a parallel surface
on the same SQLite table by treating ``owui-chat:<user_id>:<chat_id>``
as the synthetic session_id, so no new migration is needed and existing
list/set logic in the repository is reused verbatim. The snapshot file
is written to a separate subtree so the pi-adapter overlay loader can
discover it by (user_id, chat_id) without needing the synthetic key.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.storage.repositories import Repository

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_MARKS = {"active", "background", "stale", "hidden"}
OVERLAY_SCHEMA_VERSION = 1


def synthetic_session_id(user_id: str, chat_id: str) -> str:
    """Stable key used inside the session_message_overlays table."""
    return f"owui-chat:{user_id}:{chat_id}"


def chat_snapshot_path(user_id: str, chat_id: str) -> Path:
    """File pi-adapter reads at prompt-assembly time."""
    return get_settings().observation_dir / "overlays" / "chats" / user_id / f"{chat_id}.json"


def _refresh_chat_snapshot(user_id: str, chat_id: str) -> None:
    sid = synthetic_session_id(user_id, chat_id)
    try:
        overlays = Repository.from_env().list_message_overlays(sid)
        non_active = sorted(
            (
                {"index": idx, "mark": ov["mark"], "note": ov["note"]}
                for idx, ov in overlays.items()
                if ov["mark"] != "active"
            ),
            key=lambda o: o["index"],
        )
        path = chat_snapshot_path(user_id, chat_id)
        if not non_active:
            if path.exists():
                path.unlink()
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "user_id": user_id,
            "chat_id": chat_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": OVERLAY_SCHEMA_VERSION,
            "overlays": non_active,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        logger.warning("chat overlay snapshot write failed for %s/%s", user_id, chat_id, exc_info=True)


def _validate_user_chat(user_id: str, chat_id: str) -> None:
    """Basic safety: keep path components from escaping the subtree."""
    for label, val in (("user_id", user_id), ("chat_id", chat_id)):
        if not val or "/" in val or "\\" in val or val.startswith(".."):
            raise HTTPException(status_code=400, detail=f"invalid {label}")


@router.get("/api/chats/{user_id}/{chat_id}/overlay")
def get_chat_overlay(user_id: str, chat_id: str) -> dict[str, Any]:
    _validate_user_chat(user_id, chat_id)
    sid = synthetic_session_id(user_id, chat_id)
    rows = Repository.from_env().list_message_overlays(sid)
    snapshot = None
    path = chat_snapshot_path(user_id, chat_id)
    if path.exists():
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            snapshot = None
    return {
        "user_id": user_id,
        "chat_id": chat_id,
        "overlays": [
            {"index": idx, "mark": ov["mark"], "note": ov["note"], "updated_at": ov["updated_at"]}
            for idx, ov in sorted(rows.items())
        ],
        "snapshot_present": snapshot is not None,
    }


@router.post("/api/chats/{user_id}/{chat_id}/messages/{message_index}/mark")
async def set_chat_mark(user_id: str, chat_id: str, message_index: int, request: Request) -> dict[str, Any]:
    _validate_user_chat(user_id, chat_id)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc
    mark = (body.get("mark") or "").strip()
    if mark not in VALID_MARKS:
        raise HTTPException(status_code=400, detail=f"mark must be one of {sorted(VALID_MARKS)}")
    sid = synthetic_session_id(user_id, chat_id)
    row = Repository.from_env().set_message_overlay(sid, message_index, mark=mark)
    _refresh_chat_snapshot(user_id, chat_id)
    return {"ok": True, "overlay": row}


@router.post("/api/chats/{user_id}/{chat_id}/messages/{message_index}/note")
async def set_chat_note(user_id: str, chat_id: str, message_index: int, request: Request) -> dict[str, Any]:
    _validate_user_chat(user_id, chat_id)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc
    if "note" not in body:
        raise HTTPException(status_code=400, detail="body must include a 'note' field (string or null)")
    note = body["note"]
    if note is not None and not isinstance(note, str):
        raise HTTPException(status_code=400, detail="note must be a string or null")
    if isinstance(note, str) and note.strip() == "":
        note = None
    sid = synthetic_session_id(user_id, chat_id)
    row = Repository.from_env().set_message_overlay(sid, message_index, note=note)
    _refresh_chat_snapshot(user_id, chat_id)
    return {"ok": True, "overlay": row}
