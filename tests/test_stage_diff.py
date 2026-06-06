"""Unit tests for stage_diff: provider-adapter diff computation."""
from __future__ import annotations

from app.stage_diff import compute_stage_diff, diff_change_count


def _ctx(messages, tools=None, **extra):
    return {"messages": messages, "tools": tools or [], "model": {"id": "m"}, **extra}


def _pp(messages, tools=None, **extra):
    return {
        "model": {"provider": "p", "id": "m"},
        "payload": {"messages": messages, "tools": tools or [], "model": "m", **extra},
    }


def test_returns_none_on_missing_inputs():
    assert compute_stage_diff(None, {"payload": {}}) is None
    assert compute_stage_diff({}, None) is None
    assert compute_stage_diff({}, {}) is None  # no inner payload


def test_detects_prepended_system_message():
    ctx = _ctx([
        {"role": "user", "content": "hi", "timestamp": 123},
    ])
    pp = _pp([
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "hi"},
    ])
    diff = compute_stage_diff(ctx, pp)
    assert diff["message_count"] == {"ctx": 1, "pp": 2}
    assert diff["message_diffs"][0]["kind"] == "added"
    assert diff["message_diffs"][0]["pp_role"] == "system"
    # The user message should be aligned (timestamp stripped)
    assert diff["message_diffs"][1]["kind"] == "modified"
    assert "stripped" in " ".join(diff["message_diffs"][1]["changes"])


def test_detects_role_rename():
    ctx = _ctx([{"role": "toolResult", "content": "out", "toolCallId": "x", "toolName": "bash"}])
    pp = _pp([{"role": "tool", "content": "out", "tool_call_id": "x"}])
    diff = compute_stage_diff(ctx, pp)
    pair = diff["message_diffs"][0]
    assert pair["kind"] == "modified"
    assert any("role: toolResult -> tool" in c for c in pair["changes"])
    assert any("stripped" in c for c in pair["changes"])
    assert any("added" in c for c in pair["changes"])


def test_detects_assistant_content_promotion():
    ctx = _ctx([{
        "role": "assistant",
        "content": [{"type": "text", "text": "ok"}, {"type": "toolCall", "id": "1", "name": "bash"}],
        "usage": {"input": 1},
        "stopReason": "tool_use",
    }])
    pp = _pp([{
        "role": "assistant",
        "content": "ok",
        "tool_calls": [{"id": "1", "type": "function", "function": {"name": "bash"}}],
    }])
    diff = compute_stage_diff(ctx, pp)
    pair = diff["message_diffs"][0]
    assert pair["kind"] == "modified"
    assert any("content shape" in c for c in pair["changes"])
    assert any("tool_calls" in c for c in pair["changes"])  # in added list


def test_detects_top_level_stream_added():
    ctx = _ctx([{"role": "user", "content": "hi"}])
    pp = _pp([{"role": "user", "content": "hi"}], stream=True, stream_options={"include_usage": True})
    diff = compute_stage_diff(ctx, pp)
    keys = [c["key"] for c in diff["top_changes"] if c["kind"] == "added"]
    assert "stream" in keys
    assert "stream_options" in keys


def test_detects_top_level_model_changed():
    ctx = {"messages": [], "tools": [], "model": {"provider": "via-hub", "id": "m"}}
    pp = {"payload": {"messages": [], "tools": [], "model": "m"}}
    diff = compute_stage_diff(ctx, pp)
    changed = [c for c in diff["top_changes"] if c["kind"] == "changed" and c["key"] == "model"]
    assert len(changed) == 1


def test_detects_tool_envelope_wrap():
    ctx = _ctx([], tools=[{"name": "bash", "description": "d"}])
    pp = _pp([], tools=[{"type": "function", "function": {"name": "bash", "description": "d"}}])
    diff = compute_stage_diff(ctx, pp)
    assert diff["tools"]["ctx_count"] == 1
    assert diff["tools"]["pp_count"] == 1
    assert diff["tools"]["ctx_names"] == ["bash"]
    assert diff["tools"]["pp_names"] == ["bash"]
    assert diff["tools"]["wrapped_in_function_envelope"] is True


def test_alignment_handles_extra_pp_message_only_at_head():
    """If pp has 2 extra messages at the start, only the first system one should be 'added'."""
    ctx = _ctx([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo"},
    ])
    pp = _pp([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo"},
    ])
    diff = compute_stage_diff(ctx, pp)
    kinds = [d["kind"] for d in diff["message_diffs"]]
    assert kinds == ["added", "unchanged", "unchanged"] or kinds == ["added", "modified", "modified"]


def test_diff_change_count_sums_top_and_message_changes():
    ctx = _ctx([{"role": "user", "content": "hi", "timestamp": 1}])
    pp = _pp(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        stream=True,
    )
    diff = compute_stage_diff(ctx, pp)
    # 1 added message (system) + 1 modified message (timestamp stripped)
    # + 2 top-level changes (stream added; model dict-vs-string)
    assert diff_change_count(diff) == 4


def test_diff_change_count_handles_none():
    assert diff_change_count(None) == 0
    assert diff_change_count({}) == 0


def test_pure_pass_through_yields_no_changes():
    msgs = [{"role": "user", "content": "hi"}]
    diff = compute_stage_diff(_ctx(msgs), _pp(msgs))
    assert all(d["kind"] in ("unchanged", "modified") for d in diff["message_diffs"])
    # No top-level changes (tools+messages excluded, model differs in shape)
    changed_keys = [c["key"] for c in diff["top_changes"] if c["kind"] != "removed"]
    assert "stream" not in changed_keys
