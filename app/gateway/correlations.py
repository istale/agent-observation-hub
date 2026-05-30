from __future__ import annotations

from typing import Any, Iterable

from starlette.datastructures import Headers


INBOUND_HEADERS = {
    "x-agent-id": ("agent_id", None),
    "x-session-id": ("session_id", None),
    "x-channel": ("channel", None),
    "x-channel-id": ("channel_id", None),
    "x-conversation-id": ("conversation_id", None),
    "x-thread-id": ("thread_id", None),
    "x-user-id": ("user_id", None),
    "x-user-hash": ("user_hash", None),
    "x-openclaw-session-id": ("session_id", "openclaw"),
    "x-hermes-session-id": ("session_id", "hermes"),
    "x-openwebui-conversation-id": ("conversation_id", "openwebui"),
    "x-discord-channel-id": ("channel_id", "discord"),
    "x-discord-thread-id": ("thread_id", "discord"),
    "x-discord-user-id": ("user_id", "discord"),
}

UPSTREAM_HEADERS = {
    "x-litellm-call-id": ("litellm", "litellm_call_id"),
    "x-litellm-model-api-base": ("litellm", "model_api_base"),
    "llm_provider-trace-id": ("minimax", "provider_trace_id"),
    "llm_provider-x-session-id": ("minimax", "upstream_session_id"),
    "llm_provider-x-mm-request-id": ("minimax", "provider_request_id"),
    "llm_provider-minimax-request-id": ("minimax", "minimax_request_id"),
    "llm_provider-alb_request_id": ("minimax", "alb_request_id"),
}


def inbound_external_ids(headers: Headers, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    generic_source = _source_from_agent(headers.get("x-agent-id"))
    records: list[dict[str, Any]] = []
    for header, (key, fixed_source) in INBOUND_HEADERS.items():
        value = headers.get(header)
        if not value:
            continue
        source = fixed_source or generic_source
        records.append(_record(ctx, source, key, value))
    return records


def ingress_route_external_ids(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    route_id = ctx.get("ingress_route_id")
    if not route_id:
        return []
    records = [_record(ctx, "ingress_route", "route_id", str(route_id))]
    for key in ("tenant_id", "user_hash", "agent_id", "channel", "channel_id", "conversation_id"):
        value = ctx.get(key)
        if value and value != "unknown":
            records.append(_record(ctx, "ingress_route", key, str(value)))
    return records


def upstream_external_ids(headers: Headers | dict[str, str], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for header, (source, key) in UPSTREAM_HEADERS.items():
        value = headers.get(header)
        if value:
            records.append(_record(ctx, source, key, value))
    return records


def _source_from_agent(agent_id: str | None) -> str:
    value = (agent_id or "").lower()
    if "hermes" in value:
        return "hermes"
    if "openclaw" in value:
        return "openclaw"
    return "client"


def _record(ctx: dict[str, Any], source: str, key: str, value: str) -> dict[str, Any]:
    return {
        "trace_id": ctx["trace_id"],
        "run_id": ctx["run_id"],
        "llm_call_id": ctx["llm_call_id"],
        "source": source,
        "key": key,
        "value": value,
    }


def persist_external_ids(repo: Any, records: Iterable[dict[str, Any]]) -> None:
    for record in records:
        repo.insert_external_id(record)
