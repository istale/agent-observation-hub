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


def usage_from_record(record: dict[str, Any]) -> dict[str, int | None] | None:
    usage = (record.get("json") or {}).get("usage")
    if not usage:
        for line in str(record.get("raw", "")).splitlines():
            stripped = line.strip()
            if not stripped.startswith("data:"):
                continue
            data = stripped.removeprefix("data:").strip()
            if not data or data == "[DONE]":
                continue
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                continue
            usage = parsed.get("usage")
            if usage:
                break
    if not usage:
        return None
    return {
        "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
        "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
