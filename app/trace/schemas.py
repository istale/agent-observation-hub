from typing import Any, TypedDict


class RequestContextData(TypedDict, total=False):
    trace_id: str
    run_id: str
    llm_call_id: str
    tenant_id: str | None
    user_id: str | None
    user_hash: str | None
    agent_id: str | None
    session_id: str | None
    channel: str | None
    channel_id: str | None
    conversation_id: str | None
    trigger_type: str | None
    extra: dict[str, Any]
