from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.config import get_settings
from app.gateway.correlations import inbound_external_ids, ingress_route_external_ids, persist_external_ids, upstream_external_ids
from app.gateway.forwarding import downstream_response_headers, upstream_request_headers
from app.gateway.request_context import parse_request_context, response_trace_headers
from app.gateway.streaming_capture import chunk_record, usage_from_record
from app.storage.repositories import Repository
from app.trace.events import utc_now_iso
from app.trace.ids import new_event_id
from app.trace.normalizer import extract_usage
from app.trace.raw_store import RawStore


router = APIRouter()


def _repo() -> Repository:
    return Repository.from_env()


def _store() -> RawStore:
    return RawStore.from_env()


def _record_start(repo: Repository, store: RawStore, ctx: dict[str, Any], body: dict[str, Any], request_ref: str) -> None:
    repo.upsert_run({
        **ctx,
        "started_at": ctx["started_at"],
        "status": "running",
        "input_summary": body.get("model"),
    })
    repo.insert_llm_call({
        **ctx,
        "provider": "openai-compatible",
        "upstream_base_url": get_settings().upstream_openai_base_url,
        "model": body.get("model"),
        "endpoint": "/v1/chat/completions",
        "is_stream": bool(body.get("stream")),
        "request_ref": request_ref,
        "started_at": ctx["started_at"],
        "status": "running",
    })
    repo.insert_event({
        "event_id": new_event_id(),
        "trace_id": ctx["trace_id"],
        "run_id": ctx["run_id"],
        "event_type": "llm_request",
        "source": "gateway",
        "timestamp": ctx["started_at"],
        "payload_ref": request_ref,
    })
    store.append_jsonl(str(ctx["trace_id"]), "events.jsonl", {"event_type": "llm_request", "payload_ref": request_ref, "timestamp": ctx["started_at"]})
    store.write_json(str(ctx["trace_id"]), "run.json", {k: v for k, v in ctx.items() if k != "llm_call_id"})


def _finish_call(repo: Repository, ctx: dict[str, Any], started: float, *, status: str, http_status: int | None = None, response_ref: str | None = None, chunks_ref: str | None = None, usage: dict[str, int | None] | None = None, error: Exception | None = None) -> None:
    ended_at = utc_now_iso()
    update: dict[str, Any] = {
        "ended_at": ended_at,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "status": status,
        "http_status": http_status,
        "response_ref": response_ref,
        "response_chunks_ref": chunks_ref,
    }
    if usage:
        update.update(usage)
    if error:
        update["error_type"] = type(error).__name__
        update["error_message"] = str(error)
    elif status == "error" and http_status is not None:
        update["error_type"] = "HTTPError"
        update["error_message"] = f"upstream returned HTTP {http_status}"
    repo.update_llm_call(str(ctx["llm_call_id"]), {k: v for k, v in update.items() if v is not None})
    repo.update_run(str(ctx["run_id"]), {
        "ended_at": ended_at,
        "status": status,
        "failure_type": type(error).__name__ if error else ("http_error" if status == "error" else None),
    })
    repo.insert_event({
        "event_id": new_event_id(),
        "trace_id": ctx["trace_id"],
        "run_id": ctx["run_id"],
        "event_type": "llm_error" if status == "error" else "llm_response",
        "source": "gateway",
        "timestamp": ended_at,
        "status": "error" if status == "error" else "ok",
        "severity": "error" if status == "error" else "info",
        "payload_ref": response_ref or chunks_ref,
        "payload_json": {"error": str(error)} if error else None,
    })


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    settings = get_settings()
    repo = _repo()
    store = _store()
    ctx = parse_request_context(request)
    headers = response_trace_headers(ctx)
    started = time.perf_counter()

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400, headers=headers)

    request_ref = store.write_json(str(ctx["trace_id"]), f"llm_{ctx['llm_call_id']}_request.json", {"headers": dict(request.headers), "body": body})
    _record_start(repo, store, ctx, body, request_ref)
    persist_external_ids(repo, inbound_external_ids(request.headers, ctx))
    persist_external_ids(repo, ingress_route_external_ids(ctx))

    upstream_url = f"{settings.upstream_openai_base_url}/v1/chat/completions"
    timeout = httpx.Timeout(settings.request_timeout, read=settings.request_timeout)
    if body.get("stream"):
        chunks_ref = f"{store._trace_dir(str(ctx['trace_id'])).relative_to(store.root).as_posix()}/llm_{ctx['llm_call_id']}_chunks.jsonl"
        client = httpx.AsyncClient(timeout=timeout)
        stream_usage: dict[str, int | None] = {}
        try:
            upstream_request = client.build_request("POST", upstream_url, json=body, headers=upstream_request_headers(request.headers))
            upstream = await client.send(upstream_request, stream=True)
            persist_external_ids(repo, upstream_external_ids(upstream.headers, ctx))
        except Exception as exc:
            await client.aclose()
            _finish_call(repo, ctx, started, status="error", error=exc)
            return JSONResponse({"error": str(exc)}, status_code=502, headers=headers)

        async def iterator():
            try:
                async for part in upstream.aiter_bytes():
                    if part:
                        record = chunk_record(part)
                        usage = usage_from_record(record)
                        if usage:
                            stream_usage.update(usage)
                        store.append_jsonl(str(ctx["trace_id"]), f"llm_{ctx['llm_call_id']}_chunks.jsonl", record)
                    yield part
                _finish_call(repo, ctx, started, status="ok" if upstream.status_code < 400 else "error", http_status=upstream.status_code, chunks_ref=chunks_ref, usage=stream_usage or None)
            except Exception as exc:
                _finish_call(repo, ctx, started, status="error", http_status=upstream.status_code, chunks_ref=chunks_ref, error=exc)
                raise
            except asyncio.CancelledError as exc:
                _finish_call(repo, ctx, started, status="error", http_status=upstream.status_code, chunks_ref=chunks_ref, error=exc)
                raise
            finally:
                await upstream.aclose()
                await client.aclose()

        response_headers = downstream_response_headers(upstream.headers)
        response_headers.update(headers)
        return StreamingResponse(iterator(), status_code=upstream.status_code, headers=response_headers, media_type=upstream.headers.get("content-type", "text/event-stream"))

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            upstream = await client.post(upstream_url, json=body, headers=upstream_request_headers(request.headers))
        persist_external_ids(repo, upstream_external_ids(upstream.headers, ctx))
    except Exception as exc:
        _finish_call(repo, ctx, started, status="error", error=exc)
        return JSONResponse({"error": str(exc)}, status_code=502, headers=headers)

    response_ref = None
    usage = None
    try:
        response_json = upstream.json()
        response_ref = store.write_json(str(ctx["trace_id"]), f"llm_{ctx['llm_call_id']}_response.json", response_json)
        usage = extract_usage(response_json)
        body_bytes = json.dumps(response_json, ensure_ascii=False).encode("utf-8")
    except ValueError:
        body_bytes = upstream.content
        response_ref = store.write_json(str(ctx["trace_id"]), f"llm_{ctx['llm_call_id']}_response.json", {"raw": upstream.text})
    _finish_call(repo, ctx, started, status="ok" if upstream.status_code < 400 else "error", http_status=upstream.status_code, response_ref=response_ref, usage=usage)
    response_headers = downstream_response_headers(upstream.headers)
    response_headers.update(headers)
    return Response(content=body_bytes, status_code=upstream.status_code, headers=response_headers, media_type=upstream.headers.get("content-type"))


@router.post("/v1/responses")
async def responses_passthrough(request: Request) -> Response:
    settings = get_settings()
    ctx = parse_request_context(request)
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
            upstream = await client.post(f"{settings.upstream_openai_base_url}/v1/responses", content=body, headers=upstream_request_headers(request.headers))
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502, headers=response_trace_headers(ctx))
    headers = downstream_response_headers(upstream.headers)
    headers.update(response_trace_headers(ctx))
    return Response(content=upstream.content, status_code=upstream.status_code, headers=headers, media_type=upstream.headers.get("content-type"))
