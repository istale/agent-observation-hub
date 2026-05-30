from __future__ import annotations

import json
from typing import Any


def chunk_record(chunk: bytes) -> dict[str, Any]:
    text = chunk.decode("utf-8", errors="replace")
    record: dict[str, Any] = {"raw": text}
    stripped = text.strip()
    if stripped.startswith("data:"):
        data = stripped.removeprefix("data:").strip()
        record["data"] = data
        if data != "[DONE]":
            try:
                record["json"] = json.loads(data)
            except json.JSONDecodeError:
                pass
    return record
