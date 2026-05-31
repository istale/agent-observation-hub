from datetime import datetime, timedelta
from typing import Any

from app.importers.agent_events.models import NormalizedAgentEvent
from app.storage.db import db_connection
from app.storage.repositories import Repository
from app.trace.ids import new_event_id, new_run_id, new_trace_id


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _fill_from_ingress_route(repo: Repository, event: NormalizedAgentEvent) -> None:
    if not event.user_hash:
        return
    routes = [
        route for route in repo.list_ingress_routes(enabled=1)
        if route.get("user_hash") == event.user_hash
        and (not event.source or route.get("agent_id") in {None, event.source})
    ]
    if not routes:
        return
    route = sorted(routes, key=lambda item: item.get("created_at") or "", reverse=True)[0]
    event.tenant_id = event.tenant_id or route.get("tenant_id")
    event.agent_id = event.agent_id or route.get("agent_id")
    event.channel = event.channel or route.get("channel")
    event.conversation_id = event.conversation_id or route.get("conversation_id")


def _find_existing_trace(repo: Repository, event: NormalizedAgentEvent, window_minutes: int = 10) -> dict[str, Any] | None:
    if event.trace_id:
        run = repo.get_trace_run(event.trace_id)
        if run:
            return run
    if event.run_id:
        run = repo.get_run(event.run_id)
        if run:
            return run

    event_time = _parse_time(event.timestamp)
    if not event_time:
        return None
    window = timedelta(minutes=window_minutes)
    with db_connection(repo.db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM trace_runs WHERE started_at IS NOT NULL ORDER BY started_at DESC"
        ).fetchall()
    candidates = []
    for row in rows:
        run = dict(row)
        started = _parse_time(run.get("started_at"))
        ended = _parse_time(run.get("ended_at")) or started
        if not started:
            continue
        if not (started - window <= event_time <= ended + window):
            continue
        if event.session_id and event.agent_id:
            if run.get("session_id") == event.session_id and run.get("agent_id") == event.agent_id:
                candidates.append(run)
        elif event.user_hash and event.agent_id and event.channel:
            if (
                run.get("user_hash") == event.user_hash
                and run.get("agent_id") == event.agent_id
                and run.get("channel") == event.channel
            ):
                candidates.append(run)
    return candidates[0] if len(candidates) == 1 else None


def _ensure_run(repo: Repository, event: NormalizedAgentEvent) -> dict[str, Any]:
    run = _find_existing_trace(repo, event)
    if run:
        return run

    trace_id = event.trace_id or new_trace_id()
    run_id = event.run_id or new_run_id()
    repo.upsert_run({
        "run_id": run_id,
        "trace_id": trace_id,
        "tenant_id": event.tenant_id,
        "user_hash": event.user_hash,
        "agent_id": event.agent_id,
        "session_id": event.session_id,
        "channel": event.channel,
        "conversation_id": event.conversation_id,
        "trigger_type": "importer",
        "started_at": event.timestamp,
        "status": "external",
        "input_summary": f"{event.source} external event",
        "identity_source": "ingress_route" if event.tenant_id or event.agent_id or event.channel else "importer",
    })
    return repo.get_run(run_id) or {"run_id": run_id, "trace_id": trace_id}


def write_event(repo: Repository, event: NormalizedAgentEvent) -> dict[str, Any]:
    _fill_from_ingress_route(repo, event)
    run = _ensure_run(repo, event)
    payload = dict(event.payload)
    if event.message is not None:
        payload.setdefault("message", event.message)
    if event.raw_line is not None:
        payload.setdefault("raw_line", event.raw_line)
    repo.insert_event({
        "event_id": new_event_id(),
        "trace_id": run["trace_id"],
        "run_id": run["run_id"],
        "event_type": event.event_type,
        "source": event.source,
        "timestamp": event.timestamp,
        "status": event.status,
        "severity": event.severity,
        "payload_json": payload,
        "redaction_level": "redacted",
    })
    return {"trace_id": run["trace_id"], "run_id": run["run_id"]}
