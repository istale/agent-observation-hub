"""Memory Editing UI (MEU): session messages + per-message overlay.

Read-only on Pi's session JSONL. Soft marks + notes are stored in
session_message_overlays so the source-of-truth session file is never
modified.

After every mark/note change we also write an overlay snapshot file
to $AOH_OBSERVATION_DIR/overlays/<sid>.json. Pi reads this file at
prompt time (see packages/coding-agent/src/core/observation/overlay.ts)
and applies the 混合方案 (system prepend + hidden tombstone) so marks
have real effect on what the model sees.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.pi_session_reader import read_messages, session_metadata
from app.storage.repositories import Repository

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_MARKS = {"active", "background", "stale", "hidden"}
OVERLAY_SCHEMA_VERSION = 1


def _snapshot_path(session_id: str) -> Path:
    return get_settings().observation_dir / "overlays" / f"{session_id}.json"


def _refresh_overlay_snapshot(session_id: str) -> None:
    """Sync the per-session snapshot file to reflect current SQLite state.

    Snapshot contents:
      - Only non-active overlays (active = default, no Pi action needed)
      - Sorted by message_index for stable diffs
      - Atomic write via .tmp → rename

    When no non-active overlays remain, deletes the snapshot file
    entirely so Pi's loadOverlay() short-circuits cleanly.

    Failures are logged but never raised — a snapshot write failure
    must not break the user's mark/note save.
    """
    try:
        overlays = Repository.from_env().list_message_overlays(session_id)
        non_active = sorted(
            (
                {"index": idx, "mark": ov["mark"], "note": ov["note"]}
                for idx, ov in overlays.items()
                if ov["mark"] != "active"
            ),
            key=lambda o: o["index"],
        )
        path = _snapshot_path(session_id)
        if not non_active:
            # Nothing for Pi to act on. Delete the file so the reader
            # doesn't even parse it.
            if path.exists():
                path.unlink()
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "session_id": session_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": OVERLAY_SCHEMA_VERSION,
            "overlays": non_active,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        logger.warning("overlay snapshot write failed for session_id=%s", session_id, exc_info=True)


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
    _refresh_overlay_snapshot(session_id)
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
    _refresh_overlay_snapshot(session_id)
    return {"ok": True, "overlay": row}
