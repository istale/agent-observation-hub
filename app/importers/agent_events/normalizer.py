import json
from typing import Any

from app.importers.agent_events.models import NormalizedAgentEvent
from app.trace.events import utc_now_iso

EVENT_TYPES = {
    "agent_run_start",
    "agent_run_end",
    "agent_message",
    "context_build",
    "routing_decision",
    "llm_prepare",
    "tool_call",
    "tool_result",
    "tool_error",
    "channel_delivery",
    "agent_error",
    "external_log",
}


def _event_type(value: Any) -> str:
    return value if isinstance(value, str) and value in EVENT_TYPES else "external_log"


def parse_line(line: str, *, source: str, user_hash: str | None = None) -> NormalizedAgentEvent:
    raw_line = line.rstrip("\n")
    try:
        parsed = json.loads(raw_line)
    except json.JSONDecodeError:
        return NormalizedAgentEvent(
            source=source,
            event_type="external_log",
            timestamp=utc_now_iso(),
            user_hash=user_hash,
            message=raw_line,
            payload={"message": raw_line},
            raw_line=raw_line,
        )

    if not isinstance(parsed, dict):
        return NormalizedAgentEvent(
            source=source,
            event_type="external_log",
            timestamp=utc_now_iso(),
            user_hash=user_hash,
            message=str(parsed),
            payload={"message": parsed},
            raw_line=raw_line,
        )

    payload = parsed.get("payload") if isinstance(parsed.get("payload"), dict) else {
        key: value
        for key, value in parsed.items()
        if key not in {
            "source", "event_type", "timestamp", "trace_id", "run_id", "tenant_id", "user_hash",
            "agent_id", "session_id", "channel", "conversation_id", "severity", "status", "message",
        }
    }
    return NormalizedAgentEvent(
        source=str(parsed.get("source") or source),
        event_type=_event_type(parsed.get("event_type")),
        timestamp=str(parsed.get("timestamp") or utc_now_iso()),
        trace_id=parsed.get("trace_id"),
        run_id=parsed.get("run_id"),
        tenant_id=parsed.get("tenant_id"),
        user_hash=parsed.get("user_hash") or user_hash,
        agent_id=parsed.get("agent_id"),
        session_id=parsed.get("session_id"),
        channel=parsed.get("channel"),
        conversation_id=parsed.get("conversation_id"),
        severity=str(parsed.get("severity") or "info"),
        status=str(parsed.get("status") or "ok"),
        message=parsed.get("message"),
        payload=payload,
        raw_line=raw_line,
    )
