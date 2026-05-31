from dataclasses import dataclass, field
from typing import Any


@dataclass
class NormalizedAgentEvent:
    source: str
    event_type: str
    timestamp: str
    trace_id: str | None = None
    run_id: str | None = None
    tenant_id: str | None = None
    user_hash: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    channel: str | None = None
    conversation_id: str | None = None
    severity: str = "info"
    status: str = "ok"
    message: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    raw_line: str | None = None
