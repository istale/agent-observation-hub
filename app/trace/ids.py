from uuid import uuid4


def _new(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def new_trace_id() -> str:
    return _new("trace")


def new_run_id() -> str:
    return _new("run")


def new_event_id() -> str:
    return _new("evt")


def new_llm_call_id() -> str:
    return _new("llm")


def new_tool_call_id() -> str:
    return _new("tool")
