from typing import Any

from app.analysis_bundle import build_analysis_bundle
from app.payloads import current_payload_mode
from app.storage.repositories import Repository


def _trace_agent_key(trace: dict[str, Any]) -> tuple[str | None, str | None]:
    return trace.get("agent_id"), trace.get("channel")


def _summarize_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    agents: dict[tuple[str | None, str | None], int] = {}
    total_tokens = 0
    max_latency_ms = None
    llm_call_count = 0

    for trace in traces:
        status = trace.get("status")
        if status:
            statuses[status] = statuses.get(status, 0) + 1
        key = _trace_agent_key(trace)
        agents[key] = agents.get(key, 0) + 1
        total_tokens += trace.get("total_tokens") or 0
        llm_call_count += trace.get("llm_call_count") or 0
        latency = trace.get("max_latency_ms")
        if latency is not None:
            max_latency_ms = latency if max_latency_ms is None else max(max_latency_ms, latency)

    return {
        "trace_count": len(traces),
        "llm_call_count": llm_call_count,
        "total_tokens": total_tokens,
        "max_latency_ms": max_latency_ms,
        "statuses": statuses,
        "agents": [
            {"agent_id": agent_id, "channel": channel, "trace_count": count}
            for (agent_id, channel), count in sorted(agents.items(), key=lambda item: (-item[1], str(item[0])))
        ],
    }


def _strip_payloads(trace_bundle: dict[str, Any]) -> dict[str, Any]:
    stripped = dict(trace_bundle)
    stripped_calls = []
    for call in trace_bundle.get("llm_calls", []):
        metadata = call.get("metadata", {})
        stripped_calls.append({
            "metadata": metadata,
            "derived": call.get("derived", {}),
            "payload_refs": {
                "request_ref": metadata.get("request_ref"),
                "response_ref": metadata.get("response_ref"),
                "response_chunks_ref": metadata.get("response_chunks_ref"),
            },
        })
    stripped["llm_calls"] = stripped_calls
    return stripped


def build_user_analysis_bundle(
    user_hash: str,
    *,
    limit: int = 10,
    days: int | None = None,
    agent_id: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    include_payloads: bool = False,
    repo: Repository | None = None,
) -> dict[str, Any]:
    repo = repo or Repository.from_env()
    traces = repo.list_user_traces(
        user_hash,
        limit=limit,
        days=days,
        agent_id=agent_id,
        channel=channel,
        status=status,
    )
    warnings = []
    trace_bundles = []
    for trace in traces:
        bundle = build_analysis_bundle(trace["trace_id"], repo=repo)
        if not bundle:
            warnings.append(f"trace disappeared before bundle build: {trace['trace_id']}")
            continue
        trace_warnings = bundle.get("diagnostics", {}).get("warnings", [])
        warnings.extend([f"{trace['trace_id']}: {warning}" for warning in trace_warnings])
        trace_bundles.append(bundle if include_payloads else _strip_payloads(bundle))

    if not trace_bundles:
        warnings.append("no traces matched filters")

    return {
        "subject": {"user_hash": user_hash},
        "filters": {
            "limit": limit,
            "days": days,
            "agent_id": agent_id,
            "channel": channel,
            "status": status,
            "include_payloads": include_payloads,
        },
        "payload_mode": current_payload_mode(),
        "summary": _summarize_traces(traces),
        "traces": trace_bundles,
        "diagnostics": {"warnings": warnings},
    }
