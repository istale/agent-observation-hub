from fastapi import APIRouter

from app.storage.repositories import Repository
from app.user_analysis_bundle import build_user_analysis_bundle

router = APIRouter()


@router.get("/api/subjects/users")
def list_subject_users() -> dict[str, object]:
    return {"users": Repository.from_env().list_observed_users()}


@router.get("/api/subjects/users/{user_hash}/traces")
def list_subject_user_traces(
    user_hash: str,
    limit: int = 50,
    days: int | None = None,
    agent_id: str | None = None,
    channel: str | None = None,
    status: str | None = None,
) -> dict[str, object]:
    repo = Repository.from_env()
    return {
        "user_hash": user_hash,
        "filters": {
            "limit": limit,
            "days": days,
            "agent_id": agent_id,
            "channel": channel,
            "status": status,
        },
        "traces": repo.list_user_traces(
            user_hash,
            limit=limit,
            days=days,
            agent_id=agent_id,
            channel=channel,
            status=status,
        ),
    }


@router.get("/api/subjects/users/{user_hash}/analysis-bundle")
def subject_user_analysis_bundle(
    user_hash: str,
    limit: int = 10,
    days: int | None = None,
    agent_id: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    include_payloads: bool = False,
) -> dict[str, object]:
    return build_user_analysis_bundle(
        user_hash,
        limit=limit,
        days=days,
        agent_id=agent_id,
        channel=channel,
        status=status,
        include_payloads=include_payloads,
    )


@router.get("/api/subjects/users/{user_hash}/agents")
def list_subject_user_agents(user_hash: str) -> dict[str, object]:
    return {"user_hash": user_hash, "agents": Repository.from_env().list_user_agents(user_hash)}
