import re
from collections.abc import Mapping
from typing import Any


REDACTED = "[REDACTED]"
SENSITIVE_FIELD_RE = re.compile(r"(authorization|password|passwd|token|secret|api[_-]?key|access[_-]?key|private[_-]?key|key)$", re.I)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.I)
API_KEY_RE = re.compile(r"\b(?:sk|pk|rk|ak)-[A-Za-z0-9_-]{8,}\b")
SSH_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: REDACTED if SENSITIVE_FIELD_RE.search(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        text = SSH_KEY_RE.sub(REDACTED, value)
        text = BEARER_RE.sub(REDACTED, text)
        text = API_KEY_RE.sub(REDACTED, text)
        text = EMAIL_RE.sub(REDACTED, text)
        text = re.sub(r"(?i)(password|token|secret|api[_-]?key)=([^&\s]+)", rf"\1={REDACTED}", text)
        return text
    return value
