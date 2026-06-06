"""Compute structural diff between Pi's `context` event (what the agent has) and
`before_provider_payload` event (what the provider adapter built for the LLM).

Surfaces what the provider adapter mutated: system prompt prepended, roles renamed,
agent-runtime metadata stripped, reasoning/tool_calls promoted, sampling params added.
"""
from __future__ import annotations

from typing import Any

PREVIEW_CHARS = 200


def _preview(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:PREVIEW_CHARS]
    if isinstance(value, list):
        parts: list[str] = []
        for block in value:
            if isinstance(block, dict):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                else:
                    parts.append(f"[{block.get('type', 'block')}]")
            else:
                parts.append(str(block))
        return "\n".join(parts)[:PREVIEW_CHARS]
    return str(value)[:PREVIEW_CHARS]


def _content_shape(content: Any) -> str:
    if isinstance(content, str):
        return "string"
    if isinstance(content, list):
        types = {b.get("type") for b in content if isinstance(b, dict) and b.get("type")}
        if not types:
            return "list"
        return "list<" + ",".join(sorted(t for t in types if t)) + ">"
    return type(content).__name__


def _align_messages(ctx_msgs: list[dict[str, Any]], pp_msgs: list[dict[str, Any]]) -> list[tuple[dict | None, dict | None, str]]:
    """Best-effort alignment. Returns list of (ctx_msg, pp_msg, marker) tuples.

    Handles the common case where the provider adapter prepended a system message
    that isn't present in the agent context.
    """
    pairs: list[tuple[dict | None, dict | None, str]] = []
    ci = 0
    pi = 0

    while pi < len(pp_msgs):
        ctx_msg = ctx_msgs[ci] if ci < len(ctx_msgs) else None
        pp_msg = pp_msgs[pi]
        if ctx_msg is None:
            pairs.append((None, pp_msg, "added"))
            pi += 1
            continue
        if pp_msg.get("role") == "system" and ctx_msg.get("role") != "system":
            pairs.append((None, pp_msg, "added"))
            pi += 1
            continue
        pairs.append((ctx_msg, pp_msg, "pair"))
        ci += 1
        pi += 1
    while ci < len(ctx_msgs):
        pairs.append((ctx_msgs[ci], None, "removed"))
        ci += 1
    return pairs


def _diff_pair(ctx_msg: dict[str, Any] | None, pp_msg: dict[str, Any] | None) -> dict[str, Any]:
    if ctx_msg is None and pp_msg is None:
        return {"kind": "empty"}
    if ctx_msg is None:
        return {
            "kind": "added",
            "pp_role": pp_msg.get("role"),
            "pp_preview": _preview(pp_msg.get("content")),
            "pp_keys": sorted(pp_msg.keys()),
        }
    if pp_msg is None:
        return {
            "kind": "removed",
            "ctx_role": ctx_msg.get("role"),
            "ctx_preview": _preview(ctx_msg.get("content")),
            "ctx_keys": sorted(ctx_msg.keys()),
        }

    ctx_role = ctx_msg.get("role")
    pp_role = pp_msg.get("role")
    ctx_keys = set(ctx_msg.keys())
    pp_keys = set(pp_msg.keys())
    stripped = sorted(ctx_keys - pp_keys)
    added_fields = sorted(pp_keys - ctx_keys)
    changes: list[str] = []
    if ctx_role != pp_role:
        changes.append(f"role: {ctx_role} -> {pp_role}")
    ctx_shape = _content_shape(ctx_msg.get("content"))
    pp_shape = _content_shape(pp_msg.get("content"))
    if ctx_shape != pp_shape:
        changes.append(f"content shape: {ctx_shape} -> {pp_shape}")
    if stripped:
        changes.append("stripped: " + ", ".join(stripped))
    if added_fields:
        changes.append("added: " + ", ".join(added_fields))
    return {
        "kind": "modified" if changes else "unchanged",
        "ctx_role": ctx_role,
        "pp_role": pp_role,
        "ctx_preview": _preview(ctx_msg.get("content")),
        "pp_preview": _preview(pp_msg.get("content")),
        "ctx_keys": sorted(ctx_keys),
        "pp_keys": sorted(pp_keys),
        "ctx_shape": ctx_shape,
        "pp_shape": pp_shape,
        "changes": changes,
    }


def _diff_top_level(ctx: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Diff non-message top-level fields. `payload` is the inner provider payload."""
    # Take the *inner* provider payload — `before_provider_payload.payload` field — and
    # the context dict. Compare keys other than "messages" and "tools".
    excluded = {"messages", "tools"}
    out: list[dict[str, Any]] = []
    ctx_keys = {k for k in ctx.keys() if k not in excluded}
    pp_keys = {k for k in payload.keys() if k not in excluded}
    for k in sorted(pp_keys - ctx_keys):
        out.append({"kind": "added", "key": k, "value": payload[k]})
    for k in sorted(ctx_keys - pp_keys):
        out.append({"kind": "removed", "key": k, "value": ctx[k]})
    for k in sorted(ctx_keys & pp_keys):
        if ctx[k] != payload[k]:
            out.append({"kind": "changed", "key": k, "ctx_value": ctx[k], "pp_value": payload[k]})
    return out


def _diff_tools(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    ctx_tools = ctx.get("tools") or []
    pp_tools = payload.get("tools") or []
    ctx_names: list[str] = []
    for t in ctx_tools:
        if isinstance(t, dict):
            ctx_names.append(t.get("name") or "")
    pp_names: list[str] = []
    for t in pp_tools:
        if isinstance(t, dict):
            if t.get("type") == "function" and isinstance(t.get("function"), dict):
                pp_names.append(t["function"].get("name") or "")
            else:
                pp_names.append(t.get("name") or "")
    return {
        "ctx_count": len(ctx_tools),
        "pp_count": len(pp_tools),
        "ctx_names": ctx_names,
        "pp_names": pp_names,
        "wrapped_in_function_envelope": any(
            isinstance(t, dict) and t.get("type") == "function" and "function" in t for t in pp_tools
        ),
    }


# Cut 6d: hub-side knowledge of what each pi-ai adapter mutation means.
# Annotates Provider Adapter Diff items with a human-readable explanation so
# the user can answer "why did the adapter do this?" without grepping the
# openai-completions.ts source. Falls back to None when nothing matches.
def explain_top_change(change: dict[str, Any]) -> str | None:
    key = (change.get("key") or "").lower()
    kind = change.get("kind")
    if kind == "added":
        if key == "stream":
            return "openai-completions adapter always sets stream=true (Pi consumes streaming responses)"
        if key == "stream_options":
            return "compat.supportsUsageInStreaming → adapter adds stream_options:{include_usage:true} so usage tokens come back in the stream"
        if key == "store":
            return "compat.supportsStore → adapter sets store=false so OpenAI doesn't retain the request"
        if key == "prompt_cache_key":
            return "OpenAI prompt-cache key derived from sessionId for cache hits across turns"
        if key == "prompt_cache_retention":
            return "compat.supportsLongCacheRetention → adapter sets 24h retention"
        if key == "tools":
            return "context had tools; adapter wraps each in {type:'function', function:{...}} envelope"
        if key == "tool_choice":
            return "options.toolChoice set by caller"
        if key == "enable_thinking":
            return "compat.thinkingFormat (zai/qwen) → adapter emits a provider-specific thinking toggle"
        if key == "max_tokens" or key == "max_completion_tokens":
            return "options.maxTokens set; field name picked from compat.maxTokensField"
        if key == "temperature":
            return "options.temperature explicitly set by caller"
    if kind == "removed":
        return "this field is internal agent state and not sent to the LLM"
    if kind == "changed":
        if key == "model":
            return "agent stores model as {provider,id} dict; adapter flattens to a single string id for the API"
    return None


def explain_message_change(change_text: str) -> str | None:
    text = (change_text or "").lower()
    if text.startswith("role:"):
        if "toolresult -> tool" in text:
            return "OpenAI chat completions uses role='tool' for tool results (not 'toolResult')"
        if "system -> developer" in text:
            return "compat.supportsDeveloperRole + model.reasoning → reasoning-capable models use 'developer' role for the system prompt"
        if "developer -> system" in text:
            return "compat.supportsDeveloperRole=false → adapter downgrades developer role back to system"
    if "stripped:" in text and "timestamp" in text:
        return "Pi-internal AgentMessage metadata (timestamp/usage/responseId/stopReason/api/model/provider) not sent to the model"
    if "stripped:" in text and "toolcallid" in text:
        return "Pi internal toolCallId → OpenAI's tool_call_id (snake_case)"
    if "content shape" in text:
        if "->string" in text or "-> string" in text:
            return "assistant content collapsed: thinking blocks → reasoning field; toolCall blocks → tool_calls field; text → top-level content string"
    if "added: reasoning" in text or "added: tool_calls" in text:
        return "adapter promotes content sub-types into top-level fields (reasoning from thinking blocks, tool_calls from toolCall blocks)"
    return None


def annotate_diff(diff: dict[str, Any] | None) -> dict[str, Any] | None:
    """Add 'explanation' field to each diff item in-place; returns the same dict."""
    if not diff:
        return diff
    for c in diff.get("top_changes") or []:
        c["explanation"] = explain_top_change(c)
    for d in diff.get("message_diffs") or []:
        if d.get("changes"):
            d["explanations"] = [explain_message_change(c) for c in d["changes"]]
    return diff


def diff_change_count(diff: dict[str, Any] | None) -> int:
    """Total count of meaningful changes in a diff (added/removed messages, modified messages, top-level changes)."""
    if not diff:
        return 0
    count = len(diff.get("top_changes") or [])
    for d in diff.get("message_diffs") or []:
        if d.get("kind") in ("added", "removed", "modified"):
            count += 1
    return count


def compute_stage_diff(context_payload: dict[str, Any] | None, before_provider_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not context_payload or not before_provider_payload:
        return None
    # before_provider_payload looks like {"model": {...}, "payload": {...provider-built...}}
    inner = before_provider_payload.get("payload") if isinstance(before_provider_payload, dict) else None
    if not isinstance(inner, dict):
        return None
    ctx_msgs = context_payload.get("messages") or []
    pp_msgs = inner.get("messages") or []
    pairs = _align_messages(ctx_msgs, pp_msgs)
    message_diffs = [{"position": i, **_diff_pair(c, p), "marker": marker} for i, (c, p, marker) in enumerate(pairs)]
    top_changes = _diff_top_level(context_payload, inner)
    tools = _diff_tools(context_payload, inner)
    return {
        "message_count": {"ctx": len(ctx_msgs), "pp": len(pp_msgs)},
        "message_diffs": message_diffs,
        "top_changes": top_changes,
        "tools": tools,
    }
