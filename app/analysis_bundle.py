from typing import Any

from app.payloads import current_payload_mode, read_payload
from app.storage.repositories import Repository
from app.ui.formatters import llm_response_view


IDENTITY_FIELDS = [
    "tenant_id",
    "user_hash",
    "agent_id",
    "session_id",
    "channel",
    "conversation_id",
    "identity_source",
]

METADATA_FIELDS = [
    "llm_call_id",
    "trace_id",
    "run_id",
    "tenant_id",
    "user_hash",
    "agent_id",
    "session_id",
    "channel",
    "conversation_id",
    "identity_source",
    "provider",
    "upstream_base_url",
    "model",
    "endpoint",
    "is_stream",
    "started_at",
    "ended_at",
    "latency_ms",
    "status",
    "http_status",
    "error_type",
    "error_message",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "request_ref",
    "response_ref",
    "response_chunks_ref",
    "redaction_level",
]


def _identity(run: dict[str, Any]) -> dict[str, Any]:
    return {field: run.get(field) for field in IDENTITY_FIELDS}


def _metadata(call: dict[str, Any]) -> dict[str, Any]:
    return {field: call.get(field) for field in METADATA_FIELDS}


def _read_call_payloads(call: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    payloads: dict[str, Any] = {}
    refs = [
        ("request_ref", "request", "request"),
        ("response_ref", "response", "response"),
        ("response_chunks_ref", "response_chunks", "response chunks"),
    ]
    for ref_key, payload_key, label in refs:
        payload_ref = call.get(ref_key)
        if not payload_ref:
            continue
        try:
            payloads[payload_key] = read_payload(payload_ref)
        except FileNotFoundError:
            warnings.append(f"missing {label} payload: {payload_ref}")
    return payloads


def build_analysis_bundle(trace_id: str, repo: Repository | None = None) -> dict[str, Any] | None:
    repo = repo or Repository.from_env()
    run = repo.get_trace_run(trace_id)
    if not run:
        return None

    warnings: list[str] = []
    events = repo.list_events(trace_id)
    llm_calls = repo.list_llm_calls_for_trace(trace_id)
    correlations = repo.list_external_ids_for_trace(trace_id)
    call_items = []
    has_raw_request = False
    has_response = False
    has_stream_chunks = False

    if not llm_calls:
        warnings.append("no llm calls captured")

    for call in llm_calls:
        payloads = _read_call_payloads(call, warnings)
        has_raw_request = has_raw_request or bool(call.get("request_ref") and "request" in payloads and current_payload_mode() == "raw")
        has_response = has_response or bool("response" in payloads)
        has_stream_chunks = has_stream_chunks or bool("response_chunks" in payloads)
        call_items.append({
            "metadata": _metadata(call),
            "payloads": payloads,
            "derived": llm_response_view(payloads.get("response"), payloads.get("response_chunks")),
        })

    return {
        "trace_id": trace_id,
        "payload_mode": current_payload_mode(),
        "run": run,
        "identity": _identity(run),
        "timeline": events,
        "llm_calls": call_items,
        "correlations": correlations,
        "diagnostics": {
            "status": run.get("status"),
            "has_raw_request": has_raw_request,
            "has_response": has_response,
            "has_stream_chunks": has_stream_chunks,
            "llm_call_count": len(llm_calls),
            "event_count": len(events),
            "correlation_count": len(correlations),
            "warnings": warnings,
        },
    }
