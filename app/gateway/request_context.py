from fastapi import Request

from app.storage.repositories import Repository
from app.trace.events import utc_now_iso
from app.trace.ids import new_llm_call_id, new_run_id, new_trace_id


HEADER_MAP = {
    "trace_id": "X-Trace-Id",
    "run_id": "X-Run-Id",
    "tenant_id": "X-Tenant-Id",
    "user_id": "X-User-Id",
    "user_hash": "X-User-Hash",
    "agent_id": "X-Agent-Id",
    "session_id": "X-Session-Id",
    "channel": "X-Channel",
    "channel_id": "X-Channel-Id",
    "conversation_id": "X-Conversation-Id",
    "trigger_type": "X-Trigger-Type",
}


def parse_request_context(request: Request) -> dict[str, str | None]:
    data: dict[str, str | None] = {}
    header_fields = set()
    for key, header in HEADER_MAP.items():
        data[key] = request.headers.get(header)
        if data[key]:
            header_fields.add(key)
    data["trace_id"] = data["trace_id"] or new_trace_id()
    data["run_id"] = data["run_id"] or new_run_id()
    data["llm_call_id"] = new_llm_call_id()
    data["started_at"] = utc_now_iso()
    for key in ("tenant_id", "user_id", "user_hash", "agent_id", "session_id", "channel", "channel_id", "conversation_id", "trigger_type"):
        data[key] = data[key] or "unknown"
    data["identity_source"] = "headers" if header_fields & _identity_fields() else "unknown"
    _apply_ingress_route_defaults(request, data)
    return data


def _identity_fields() -> set[str]:
    return {"tenant_id", "user_id", "user_hash", "agent_id", "session_id", "channel", "channel_id", "conversation_id"}


def _apply_ingress_route_defaults(request: Request, data: dict[str, str | None]) -> None:
    missing = {key for key in _identity_fields() if data.get(key) in {None, "unknown", ""}}
    if not missing:
        return
    route = Repository.from_env().find_ingress_route(
        listen_host=request.url.hostname,
        listen_port=request.url.port,
        path=request.url.path,
    )
    if not route:
        return
    filled = False
    for key in _identity_fields():
        if data.get(key) in {None, "unknown", ""} and route.get(key):
            data[key] = route[key]
            filled = True
    if not filled:
        return
    data["ingress_route_id"] = str(route["id"])
    if data.get("identity_source") == "headers":
        data["identity_source"] = "mixed"
    else:
        data["identity_source"] = "ingress_route"


def response_trace_headers(ctx: dict[str, str | None]) -> dict[str, str]:
    return {
        "X-Trace-Id": str(ctx["trace_id"]),
        "X-Run-Id": str(ctx["run_id"]),
        "X-LLM-Call-Id": str(ctx["llm_call_id"]),
    }
