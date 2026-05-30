from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")


def taipei_time(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value)
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M:%S Taipei")


def llm_response_view(response: Any | None, chunks: list[Any] | None = None) -> dict[str, str]:
    if chunks:
        return _stream_response_view(chunks)
    if not isinstance(response, dict):
        return {"assistant_text": "", "reasoning_text": ""}

    texts: list[str] = []
    reasoning: list[str] = []
    for choice in response.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message") or {}
        if isinstance(message, dict):
            _append_text(texts, message.get("content"))
            _append_text(reasoning, message.get("reasoning_content"))
            provider_fields = message.get("provider_specific_fields") or {}
            if isinstance(provider_fields, dict):
                _append_text(reasoning, provider_fields.get("reasoning_content"))

    return {
        "assistant_text": "".join(texts),
        "reasoning_text": _dedupe_join(reasoning),
    }


def _stream_response_view(chunks: list[Any]) -> dict[str, str]:
    texts: list[str] = []
    reasoning: list[str] = []
    for chunk in chunks:
        for payload in _iter_sse_payloads(chunk):
            for choice in payload.get("choices") or []:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta") or {}
                if isinstance(delta, dict):
                    _append_text(texts, delta.get("content"))
                    _append_text(reasoning, delta.get("reasoning_content"))
    return {
        "assistant_text": "".join(texts),
        "reasoning_text": _dedupe_join(reasoning),
    }


def _iter_sse_payloads(record: Any) -> list[dict[str, Any]]:
    raw = record.get("raw") if isinstance(record, dict) else record
    payloads: list[dict[str, Any]] = []
    for line in str(raw or "").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if data == "[DONE]":
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _append_text(target: list[str], value: Any) -> None:
    if isinstance(value, str) and value:
        target.append(value)


def _dedupe_join(values: list[str]) -> str:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return "\n".join(deduped)
