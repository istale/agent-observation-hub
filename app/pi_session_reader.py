"""Read Pi's session JSONL files from ~/.pi/agent/sessions/**.

Pi's session tree is JSONL: each line is an entry of various types
(session / model_change / thinking_level_change / message / compaction /
branch_point / ...). For the Memory Editing UI we focus on type='message'
entries, which carry the actual user / assistant / toolResult conversation.

We index by the session_id (UUID part of the filename + `session` entry's
`id` field) so the hub can look up "which JSONL is this trace's session?".
Cached after first scan; scan is cheap on local SSD.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _root_dir() -> Path:
    override = os.environ.get("AOH_PI_SESSIONS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".pi" / "agent" / "sessions"


@dataclass
class SessionFile:
    path: Path
    session_id: str
    cwd: str | None
    started_at: str | None


_session_index_cache: dict[str, SessionFile] | None = None


def _build_session_index() -> dict[str, SessionFile]:
    index: dict[str, SessionFile] = {}
    root = _root_dir()
    if not root.exists():
        return index
    for path in root.rglob("*.jsonl"):
        try:
            with path.open("r", encoding="utf-8") as f:
                first_line = f.readline()
                if not first_line:
                    continue
                entry = json.loads(first_line)
                if entry.get("type") != "session":
                    continue
                sid = entry.get("id")
                if not sid:
                    continue
                index[sid] = SessionFile(
                    path=path,
                    session_id=sid,
                    cwd=entry.get("cwd"),
                    started_at=entry.get("timestamp"),
                )
        except (OSError, json.JSONDecodeError):
            continue
    return index


def _index() -> dict[str, SessionFile]:
    global _session_index_cache
    if _session_index_cache is None:
        _session_index_cache = _build_session_index()
    return _session_index_cache


def invalidate_cache() -> None:
    global _session_index_cache
    _session_index_cache = None


def find_session_file(session_id: str) -> SessionFile | None:
    sf = _index().get(session_id)
    if sf is not None:
        return sf
    invalidate_cache()
    return _index().get(session_id)


def list_known_sessions() -> list[SessionFile]:
    return sorted(_index().values(), key=lambda s: s.started_at or "", reverse=True)


def _flatten_content(content: Any) -> dict[str, Any]:
    if isinstance(content, str):
        return {"text": content, "blocks": [{"type": "text", "text": content}], "has_thinking": False, "has_tool_call": False}
    if isinstance(content, list):
        text_parts: list[str] = []
        has_thinking = False
        has_tool_call = False
        for block in content:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t == "text" and isinstance(block.get("text"), str):
                text_parts.append(block["text"])
            elif t == "thinking" and isinstance(block.get("text"), str):
                has_thinking = True
            elif t == "toolCall":
                has_tool_call = True
                text_parts.append(f"[toolCall: {block.get('name','?')} id={block.get('id','?')}]")
            elif t == "image":
                text_parts.append("[image]")
        return {"text": "\n".join(text_parts), "blocks": content, "has_thinking": has_thinking, "has_tool_call": has_tool_call}
    return {"text": str(content), "blocks": [], "has_thinking": False, "has_tool_call": False}


def read_messages(session_id: str) -> list[dict[str, Any]] | None:
    """Return ordered list of message-type entries with extracted fields."""
    sf = find_session_file(session_id)
    if sf is None:
        return None
    messages: list[dict[str, Any]] = []
    try:
        with sf.path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("type") != "message":
                    continue
                msg = e.get("message", {}) or {}
                flat = _flatten_content(msg.get("content"))
                messages.append({
                    "index": len(messages),
                    "entry_id": e.get("id"),
                    "parent_id": e.get("parentId"),
                    "role": msg.get("role", "?"),
                    "timestamp": msg.get("timestamp") or e.get("timestamp"),
                    "tool_name": msg.get("toolName"),
                    "tool_call_id": msg.get("toolCallId"),
                    "model": msg.get("model"),
                    "provider": msg.get("provider"),
                    "stop_reason": msg.get("stopReason"),
                    "is_error": msg.get("isError"),
                    "text": flat["text"],
                    "blocks": flat["blocks"],
                    "has_thinking": flat["has_thinking"],
                    "has_tool_call": flat["has_tool_call"],
                    "raw_message": msg,
                })
    except OSError:
        return None
    return messages


def session_metadata(session_id: str) -> dict[str, Any] | None:
    sf = find_session_file(session_id)
    if sf is None:
        return None
    return {
        "session_id": sf.session_id,
        "cwd": sf.cwd,
        "started_at": sf.started_at,
        "jsonl_path": str(sf.path),
    }
