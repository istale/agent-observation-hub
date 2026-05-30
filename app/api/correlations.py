from fastapi import APIRouter

from app.storage.repositories import Repository

router = APIRouter()


@router.get("/api/traces/{trace_id}/correlations")
def trace_correlations(trace_id: str) -> dict[str, object]:
    return {"trace_id": trace_id, "correlations": Repository.from_env().list_external_ids_for_trace(trace_id)}


@router.get("/api/correlations")
def find_correlations(source: str | None = None, key: str | None = None, value: str | None = None, limit: int = 100) -> dict[str, object]:
    return {"matches": Repository.from_env().find_external_ids(source=source, key=key, value=value, limit=limit)}
