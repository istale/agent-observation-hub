"""View helpers for agent events: load referenced payloads and shape per-stage views."""
from __future__ import annotations

import json
from typing import Any

from app.config import get_settings

TRUNCATE_CHARS = 800


def _read_ref(payload_ref: str | None) -> Any:
    """Read a payload referenced by agent_events.payload_ref.

    payload_ref is stored relative to data_dir/raw (same convention as
    llm_calls.request_ref) so /api/raw/{ref} can serve it. Older rows that
    started with "raw/" were normalized by migration 006.
    """
    if not payload_ref:
        return None
    settings = get_settings()
    path = settings.data_dir / "raw" / payload_ref
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _decode_payload(event: dict[str, Any]) -> Any:
    if event.get("payload_inline"):
        try:
            return json.loads(event["payload_inline"])
        except Exception:
            return event["payload_inline"]
    return _read_ref(event.get("payload_ref"))


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= TRUNCATE_CHARS:
        return text, False
    return text[:TRUNCATE_CHARS], True


def _flatten_content(content: Any) -> tuple[str, list[dict[str, Any]]]:
    """Return (joined_text_preview, raw_blocks). raw_blocks is the original list/structure."""
    if isinstance(content, str):
        return content, [{"type": "text", "text": content}]
    if isinstance(content, list):
        text_parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                t = block.get("type")
                if t == "text" and isinstance(block.get("text"), str):
                    text_parts.append(block["text"])
                elif t == "toolUse":
                    text_parts.append(f"[toolUse {block.get('name', '?')} id={block.get('id', '?')}]")
                elif t == "toolResult":
                    text_parts.append(f"[toolResult id={block.get('toolUseId', '?')}]")
                elif t == "image":
                    text_parts.append("[image]")
                else:
                    text_parts.append(f"[{t}]")
        return "\n".join(text_parts), content
    return json.dumps(content, ensure_ascii=False), [{"type": "raw", "text": str(content)}]


def _shape_context(payload: dict[str, Any]) -> dict[str, Any]:
    messages = payload.get("messages") or []
    tools = payload.get("tools") or []
    cards = []
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        text_preview, blocks = _flatten_content(msg.get("content"))
        truncated, did_truncate = _truncate(text_preview)
        cards.append({
            "index": i,
            "role": msg.get("role", "?"),
            "preview": truncated,
            "truncated": did_truncate,
            "full_text": text_preview,
            "blocks": blocks,
            "tool_use_id": msg.get("toolUseId"),
        })
    tool_cards = []
    for t in tools:
        if isinstance(t, dict):
            tool_cards.append({"name": t.get("name", "?"), "description": t.get("description", "")[:200]})
    return {
        "kind": "context",
        "message_count": len(messages),
        "tool_count": len(tools),
        "messages": cards,
        "tools": tool_cards,
        "model": payload.get("model"),
    }


def _shape_before_agent_start(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload.get("raw_user_text") or ""
    truncated, did_truncate = _truncate(text)
    return {
        "kind": "before_agent_start",
        "user_text_preview": truncated,
        "user_text_truncated": did_truncate,
        "user_text_full": text,
        "image_count": payload.get("image_count", 0),
        "source": payload.get("source"),
    }


def _shape_resource_loaded(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "resource_loaded",
        "cwd": payload.get("cwd"),
        "agent_dir": payload.get("agentDir"),
        "skills": payload.get("skills") or [],
        "prompt_templates": payload.get("prompt_templates") or [],
        "agents_files": payload.get("agents_files") or [],
    }


def _stringify_args(args: Any) -> str:
    if args is None:
        return ""
    if isinstance(args, str):
        return args
    try:
        return json.dumps(args, ensure_ascii=False, indent=2)
    except Exception:
        return str(args)


def _stringify_result(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        parts: list[str] = []
        for block in result:
            if isinstance(block, dict):
                t = block.get("type")
                if t == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                else:
                    parts.append(json.dumps(block, ensure_ascii=False))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    try:
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception:
        return str(result)


def _shape_tool_call(payload: dict[str, Any]) -> dict[str, Any]:
    args_text = _stringify_args(payload.get("args"))
    preview, did_truncate = _truncate(args_text)
    return {
        "kind": "tool_call",
        "tool_name": payload.get("tool_name"),
        "tool_call_id": payload.get("tool_call_id"),
        "args_preview": preview,
        "args_truncated": did_truncate,
        "args_full": args_text,
    }


def _shape_tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    result_text = _stringify_result(payload.get("result"))
    preview, did_truncate = _truncate(result_text)
    return {
        "kind": "tool_result",
        "tool_name": payload.get("tool_name"),
        "tool_call_id": payload.get("tool_call_id"),
        "is_error": bool(payload.get("is_error")),
        "duration_ms": payload.get("duration_ms"),
        "result_preview": preview,
        "result_truncated": did_truncate,
        "result_full": result_text,
    }


def _shape_before_provider_payload(payload: dict[str, Any]) -> dict[str, Any]:
    inner = payload.get("payload") if isinstance(payload, dict) else None
    summary = {}
    if isinstance(inner, dict):
        summary = {
            "model": inner.get("model"),
            "message_count": len(inner.get("messages") or []) if isinstance(inner.get("messages"), list) else None,
            "tool_count": len(inner.get("tools") or []) if isinstance(inner.get("tools"), list) else None,
            "temperature": inner.get("temperature"),
            "stream": inner.get("stream"),
            "max_tokens": inner.get("max_tokens"),
        }
    return {"kind": "before_provider_payload", "summary": summary, "raw_keys": list(inner.keys()) if isinstance(inner, dict) else []}


SHAPERS = {
    "context": _shape_context,
    "before_agent_start": _shape_before_agent_start,
    "resource_loaded": _shape_resource_loaded,
    "before_provider_payload": _shape_before_provider_payload,
    "tool_call": _shape_tool_call,
    "tool_result": _shape_tool_result,
}


def enrich_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for ev in events:
        copy = dict(ev)
        payload = _decode_payload(ev)
        copy["payload"] = payload
        shaper = SHAPERS.get(ev.get("stage", ""))
        copy["view"] = shaper(payload) if shaper and isinstance(payload, dict) else {"kind": "raw", "preview": json.dumps(payload, ensure_ascii=False)[:TRUNCATE_CHARS] if payload is not None else ""}
        enriched.append(copy)
    return enriched
