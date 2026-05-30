from typing import Any

from app.config import get_settings
from app.trace.raw_store import RawStore
from app.trace.redaction import redact


def current_payload_mode() -> str:
    return get_settings().payload_mode


def payload_label() -> str:
    return "Raw" if current_payload_mode() == "raw" else "Redacted"


def apply_payload_policy(payload: Any) -> Any:
    return payload if current_payload_mode() == "raw" else redact(payload)


def read_payload(payload_ref: str) -> Any:
    store = RawStore.from_env()
    if payload_ref.endswith(".jsonl"):
        payload = store.read_jsonl(payload_ref)
    else:
        payload = store.read(payload_ref)
    return apply_payload_policy(payload)
