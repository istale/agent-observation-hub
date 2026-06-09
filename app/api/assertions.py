"""Composite assertion endpoints for AI-driven regression testing.

Designed so an AI agent can verify feature health without SQLite or
filesystem access. The agent invokes a known action (e.g. mark a
message, run pi --resume), then GETs the relevant assertion endpoint
and reads structured fields it can compare against expectations.

Endpoints under /api/assertions/:
  - overlay/{session_id}                 ← snapshot + DB state
  - overlay-applied/{session_id}?since   ← latest overlay_applied events
  - payload-inspect/{trace_id}           ← structured analysis of the
                                            actual LLM HTTP body
  - session-summary/{session_id}?since   ← composite for one session

All endpoints are read-only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.storage.db import db_connection
from app.storage.repositories import Repository

router = APIRouter()


# ---------- helpers ----------

def _read_payload_ref(payload_ref: str | None) -> dict[str, Any] | None:
    if not payload_ref:
        return None
    settings = get_settings()
    path = settings.data_dir / "raw" / payload_ref
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _overlay_snapshot(session_id: str) -> dict[str, Any] | None:
    path = get_settings().observation_dir / "overlays" / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------- /api/assertions/overlay/{session_id} ----------

@router.get("/api/assertions/overlay/{session_id}")
def overlay_state(session_id: str) -> dict[str, Any]:
    """Current overlay state for one session: both the SQLite truth + the
    snapshot file Pi reads. An AI agent can use this to assert:
    'I just marked turn N as stale; is the snapshot showing it?'
    """
    repo_overlays = Repository.from_env().list_message_overlays(session_id)
    snapshot = _overlay_snapshot(session_id)
    non_active = {idx: ov for idx, ov in repo_overlays.items() if ov.get("mark") != "active"}

    # Deep consistency: compare (index, mark, note) triples between DB
    # non-active rows and snapshot.overlays. A length-only check would
    # silently PASS when e.g. a mark flipped stale→background but the
    # snapshot writer failed mid-way and kept the old triple — exactly
    # the kind of drift AI-driven regression must catch.
    def _triples_from_db() -> set[tuple[int, str, str | None]]:
        return {(int(idx), ov["mark"], ov.get("note")) for idx, ov in non_active.items()}

    def _triples_from_snapshot() -> set[tuple[int, str, str | None]]:
        if snapshot is None:
            return set()
        out: set[tuple[int, str, str | None]] = set()
        for o in snapshot.get("overlays", []) or []:
            out.add((int(o.get("index")), o.get("mark"), o.get("note")))
        return out

    db_triples = _triples_from_db()
    snap_triples = _triples_from_snapshot()
    if snapshot is None:
        consistent = len(non_active) == 0
        drift: list[dict[str, Any]] = []
    else:
        consistent = db_triples == snap_triples
        drift = []
        for missing in sorted(db_triples - snap_triples):
            drift.append({"side": "db_only", "index": missing[0], "mark": missing[1], "note": missing[2]})
        for extra in sorted(snap_triples - db_triples):
            drift.append({"side": "snapshot_only", "index": extra[0], "mark": extra[1], "note": extra[2]})

    return {
        "session_id": session_id,
        "db": {
            "all_count": len(repo_overlays),
            "non_active_count": len(non_active),
            "overlays": [
                {"index": idx, "mark": ov["mark"], "note": ov["note"], "updated_at": ov["updated_at"]}
                for idx, ov in sorted(repo_overlays.items())
            ],
        },
        "snapshot": {
            "exists": snapshot is not None,
            "path": str(get_settings().observation_dir / "overlays" / f"{session_id}.json"),
            "content": snapshot,
        },
        "consistent": consistent,
        "drift": drift,
    }


# ---------- /api/assertions/payload-inspect/{trace_id} ----------

@router.get("/api/assertions/payload-inspect/{trace_id}")
def payload_inspect(trace_id: str) -> dict[str, Any]:
    """Structured analysis of one model call's HTTP payload. The agent
    reads this instead of fetching + parsing the raw JSON itself.
    """
    with db_connection(get_settings().database_path) as conn:
        row = conn.execute(
            """
            SELECT payload_ref, payload_inline FROM agent_events
            WHERE trace_id = ? AND stage = 'before_provider_payload'
            ORDER BY id DESC LIMIT 1
            """,
            (trace_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"no before_provider_payload for trace {trace_id}")
    payload_wrapper = None
    if row["payload_inline"]:
        try:
            payload_wrapper = json.loads(row["payload_inline"])
        except Exception:
            pass
    if payload_wrapper is None:
        payload_wrapper = _read_payload_ref(row["payload_ref"])
    if not payload_wrapper:
        raise HTTPException(status_code=500, detail="payload could not be loaded")
    inner = payload_wrapper.get("payload") if isinstance(payload_wrapper, dict) else None
    if not isinstance(inner, dict):
        raise HTTPException(status_code=500, detail="payload shape unexpected")
    messages: list[dict[str, Any]] = inner.get("messages") or []

    # Detect annotation in first system message
    first_system_content = ""
    for m in messages:
        if m.get("role") == "system":
            c = m.get("content")
            if isinstance(c, str):
                first_system_content = c
                break
    annotation_present = (
        "user has annotated this conversation" in first_system_content
        or "STALE" in first_system_content
        or "BACKGROUND" in first_system_content
        or "HIDDEN" in first_system_content
    )
    annotation_mentions: list[str] = []
    for kind in ("STALE", "BACKGROUND", "HIDDEN"):
        if kind in first_system_content:
            annotation_mentions.append(kind)

    # Detect hidden tombstones + check pairing
    TOMBSTONE_MARK = "elided by user"
    tombstoned: list[dict[str, Any]] = []
    pairing_issues: list[str] = []
    for i, m in enumerate(messages):
        c = m.get("content")
        is_tombstone = False
        text_repr = ""
        if isinstance(c, str):
            text_repr = c
            is_tombstone = TOMBSTONE_MARK in c
        elif isinstance(c, list) and c:
            first = c[0]
            if isinstance(first, dict) and first.get("type") == "text":
                text_repr = first.get("text", "")
                is_tombstone = TOMBSTONE_MARK in text_repr
        if is_tombstone:
            role = m.get("role")
            tool_call_id = m.get("tool_call_id")
            entry = {
                "payload_index": i,
                "role": role,
                "tool_call_id": tool_call_id,
                "pairing_intact": (role != "tool") or bool(tool_call_id),
            }
            tombstoned.append(entry)
            if entry["pairing_intact"] is False:
                pairing_issues.append(f"tombstoned tool at index {i} missing tool_call_id")

    return {
        "trace_id": trace_id,
        "payload_message_count": len(messages),
        "first_system_msg_chars": len(first_system_content),
        "annotation_in_system_prompt": annotation_present,
        "annotation_mentions": annotation_mentions,
        "tombstoned": tombstoned,
        "tombstoned_count": len(tombstoned),
        "tool_pairing_intact": len(pairing_issues) == 0,
        "pairing_issues": pairing_issues,
    }


# ---------- /api/assertions/overlay-applied/{session_id} ----------

@router.get("/api/assertions/overlay-applied/{session_id}")
def overlay_applied(session_id: str, since: str | None = None, limit: int = 20) -> dict[str, Any]:
    """List overlay_applied events for the session optionally filtered by
    timestamp. Agent uses this to assert "after I resumed pi, did
    overlay actually fire?".
    """
    repo = Repository.from_env()
    events = repo.list_agent_events_by_session(session_id)
    overlays = [e for e in events if e.get("stage") == "overlay_applied"]
    if since:
        overlays = [e for e in overlays if (e.get("ts") or "") >= since]
    overlays = overlays[-limit:] if limit else overlays
    shaped: list[dict[str, Any]] = []
    for e in overlays:
        payload = None
        if e.get("payload_inline"):
            try:
                payload = json.loads(e["payload_inline"])
            except Exception:
                payload = None
        if payload is None:
            payload = _read_payload_ref(e.get("payload_ref"))
        shaped.append({
            "trace_id": e["trace_id"],
            "ts": e["ts"],
            "event_seq": e.get("event_seq"),
            "payload": payload or {},
        })
    return {
        "session_id": session_id,
        "since": since,
        "count": len(shaped),
        "events": shaped,
    }


# ---------- /api/assertions/session-summary/{session_id} ----------

@router.get("/api/assertions/session-summary/{session_id}")
def session_summary(session_id: str, since: str | None = None) -> dict[str, Any]:
    """One-shot composite: overlay state + per-model-call analysis.
    The AI agent reads this single response to validate a whole
    scenario without N follow-up calls.
    """
    repo = Repository.from_env()
    overlay = overlay_state(session_id)
    events = repo.list_agent_events_by_session(session_id)
    if since:
        events = [e for e in events if (e.get("ts") or "") >= since]

    # Group by trace_id
    by_trace: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        by_trace.setdefault(e["trace_id"], []).append(e)

    model_calls: list[dict[str, Any]] = []
    for tid, group in by_trace.items():
        stages = {e["stage"] for e in group}
        if "before_provider_payload" not in stages:
            continue  # not a model call
        overlay_event = next((e for e in group if e["stage"] == "overlay_applied"), None)
        overlay_payload: dict[str, Any] = {}
        if overlay_event and overlay_event.get("payload_inline"):
            try:
                overlay_payload = json.loads(overlay_event["payload_inline"])
            except Exception:
                pass
        try:
            inspect = payload_inspect(tid)
        except HTTPException:
            inspect = None
        first_ts = min(e.get("ts") or "" for e in group)
        model_calls.append({
            "trace_id": tid,
            "started_at": first_ts,
            "overlay_applied": {
                "fired": overlay_event is not None,
                "overlay_count": overlay_payload.get("overlay_count", 0),
                "stale_count": overlay_payload.get("stale_count", 0),
                "background_count": overlay_payload.get("background_count", 0),
                "hidden_count": overlay_payload.get("hidden_count", 0),
                "applied_indices": overlay_payload.get("applied_indices", []),
            },
            "payload_inspection": inspect,
        })

    return {
        "session_id": session_id,
        "since": since,
        "overlay": overlay,
        "model_call_count": len(model_calls),
        "model_calls": sorted(model_calls, key=lambda c: c["started_at"]),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
