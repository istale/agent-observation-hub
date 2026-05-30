from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.trace.raw_store import RawStore
from app.trace.redaction import redact

router = APIRouter()


@router.get("/api/raw/{payload_ref:path}")
def get_raw(payload_ref: str, raw: bool = Query(False)) -> object:
    settings = get_settings()
    store = RawStore.from_env()
    try:
        if payload_ref.endswith(".jsonl"):
            payload = store.read_jsonl(payload_ref)
        else:
            payload = store.read(payload_ref)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="payload not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return payload if raw and settings.allow_raw_view else redact(payload)
