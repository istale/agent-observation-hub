from fastapi import APIRouter, HTTPException

from app.storage.repositories import Repository

router = APIRouter()


@router.get("/api/traces")
def list_traces(limit: int = 50) -> dict[str, object]:
    return {"traces": Repository.from_env().list_traces(limit)}


@router.get("/api/traces/{trace_id}")
def get_trace(trace_id: str) -> dict[str, object]:
    repo = Repository.from_env()
    run = repo.get_trace_run(trace_id)
    if not run:
        raise HTTPException(status_code=404, detail="trace not found")
    return {"run": run, "events": repo.list_events(trace_id), "llm_calls": repo.list_llm_calls_for_trace(trace_id)}


@router.get("/api/traces/{trace_id}/events")
def trace_events(trace_id: str) -> dict[str, object]:
    return {"events": Repository.from_env().list_events(trace_id)}


@router.get("/api/traces/{trace_id}/llm-calls")
def trace_llm_calls(trace_id: str) -> dict[str, object]:
    return {"llm_calls": Repository.from_env().list_llm_calls_for_trace(trace_id)}
