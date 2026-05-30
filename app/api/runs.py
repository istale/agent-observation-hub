from fastapi import APIRouter, HTTPException

from app.storage.repositories import Repository

router = APIRouter()


@router.get("/api/runs")
def list_runs(limit: int = 50) -> dict[str, object]:
    return {"runs": Repository.from_env().list_runs(limit)}


@router.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, object]:
    run = Repository.from_env().get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run": run}
