"""Pinned constraints API.

A constraint is a short rule pinned by the user (e.g. "prefer grep over
vector RAG", "reply in traditional Chinese"). Pi reads the constraint
file each turn and prepends the rules to the user prompt.

Whenever the DB changes, the constraint snapshot is written atomically
to $AOH_OBSERVATION_DIR/constraints.json so Pi sees the new state on
its next prompt without restart.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.storage.repositories import Repository

router = APIRouter()


def _snapshot_path() -> Path:
    return get_settings().observation_dir / "constraints.json"


def _write_snapshot(constraints: list[dict[str, Any]]) -> None:
    path = _snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "constraints": [
            {"id": c["id"], "text": c["text"], "scope": c.get("scope", "global"), "created_at": c.get("created_at")}
            for c in constraints
        ],
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _refresh_snapshot() -> list[dict[str, Any]]:
    constraints = Repository.from_env().list_pinned_constraints()
    _write_snapshot(constraints)
    return constraints


@router.post("/api/constraints")
async def add_constraint(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    scope = (body.get("scope") or "global").strip()
    cid = f"c_{uuid.uuid4().hex[:12]}"
    Repository.from_env().insert_pinned_constraint({"id": cid, "text": text, "scope": scope})
    _refresh_snapshot()
    return {"ok": True, "id": cid}


@router.get("/api/constraints")
def list_constraints(scope: str | None = None) -> dict[str, Any]:
    return {"constraints": Repository.from_env().list_pinned_constraints(scope)}


@router.delete("/api/constraints/{constraint_id}")
def delete_constraint(constraint_id: str) -> dict[str, Any]:
    deleted = Repository.from_env().delete_pinned_constraint(constraint_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="not found")
    _refresh_snapshot()
    return {"ok": True}
