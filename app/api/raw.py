from fastapi import APIRouter, HTTPException, Query

from app.payloads import read_payload

router = APIRouter()


@router.get("/api/raw/{payload_ref:path}")
def get_raw(payload_ref: str, raw: bool = Query(False)) -> object:
    try:
        return read_payload(payload_ref)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="payload not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
