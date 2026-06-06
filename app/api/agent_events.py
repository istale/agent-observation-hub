from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.storage.repositories import Repository

router = APIRouter()

INLINE_MAX_BYTES = 4096


def _store_payload(trace_id: str, event_seq: int | None, stage: str, payload: Any) -> tuple[str | None, str | None]:
    """Return (payload_inline, payload_ref). Small payloads stored inline; large to file."""
    if payload is None:
        return None, None
    encoded = json.dumps(payload, ensure_ascii=False)
    if len(encoded.encode("utf-8")) <= INLINE_MAX_BYTES:
        return encoded, None
    settings = get_settings()
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target_dir: Path = settings.data_dir / "raw" / date / f"trace_{trace_id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    seq_part = f"_{event_seq}" if event_seq is not None else ""
    target = target_dir / f"agent_event{seq_part}_{stage}.json"
    target.write_text(encoded, encoding="utf-8")
    return None, str(target.relative_to(settings.data_dir))


@router.post("/api/agent-events")
async def ingest_agent_event(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc

    trace_id = body.get("trace_id")
    stage = body.get("stage")
    if not trace_id or not stage:
        raise HTTPException(status_code=400, detail="trace_id and stage are required")

    event_seq = body.get("event_seq")
    payload_inline, payload_ref = _store_payload(trace_id, event_seq, stage, body.get("payload"))

    repo = Repository.from_env()
    row_id = repo.insert_agent_event({
        "trace_id": trace_id,
        "session_id": body.get("session_id"),
        "event_seq": event_seq,
        "stage": stage,
        "source_module": body.get("source_module"),
        "ts": body.get("ts") or datetime.now(timezone.utc).isoformat(),
        "payload_ref": payload_ref,
        "payload_inline": payload_inline,
    })
    return {"ok": True, "id": row_id}


@router.get("/api/traces/{trace_id}/agent-events")
def list_agent_events(trace_id: str) -> dict[str, Any]:
    return {"agent_events": Repository.from_env().list_agent_events(trace_id)}


@router.get("/api/sessions/{session_id}/agent-events")
def list_agent_events_by_session(session_id: str, limit: int = 200) -> dict[str, Any]:
    return {"agent_events": Repository.from_env().list_agent_events_by_session(session_id, limit)}
