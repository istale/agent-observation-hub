from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import asyncio

from app.api.agent_events import router as agent_events_router
from app.api.constraints import router as constraints_router
from app.config import get_settings
from app.observation_tailer import run_tailer
from app.api.correlations import router as correlations_router
from app.api.health import router as health_router
from app.api.llm_calls import router as llm_calls_router
from app.api.raw import router as raw_router
from app.api.runs import router as runs_router
from app.api.subjects import router as subjects_router
from app.api.traces import router as traces_router
from app.gateway.openai_proxy import router as openai_router
from app.logging_config import configure_logging
from app.payloads import current_payload_mode, payload_label, read_payload
from app.storage.db import init_db
from app.storage.repositories import Repository
from app.ui.formatters import llm_response_view, pretty_json, taipei_time


templates = Jinja2Templates(directory="app/ui/templates")
templates.env.filters["taipei_time"] = taipei_time
templates.env.filters["pretty_json"] = pretty_json


def _load_call_payloads(call: dict) -> tuple[dict, dict[str, str]]:
    payloads = {}
    for key in ("request_ref", "response_ref"):
        if call.get(key):
            payloads[key.removesuffix("_ref")] = read_payload(call[key])
    if call.get("response_chunks_ref"):
        payloads["chunks"] = read_payload(call["response_chunks_ref"])
    return payloads, llm_response_view(payloads.get("response"), payloads.get("chunks"))


def create_app() -> FastAPI:
    configure_logging()
    init_db()
    app = FastAPI(title="Agent Observation Hub")
    app.mount("/static", StaticFiles(directory="app/ui/static"), name="static")

    tailer_task: asyncio.Task[None] | None = None

    @app.on_event("startup")
    async def _start_tailer() -> None:
        nonlocal tailer_task
        if get_settings().observation_tail_enabled:
            tailer_task = asyncio.create_task(run_tailer())

    @app.on_event("shutdown")
    async def _stop_tailer() -> None:
        if tailer_task is not None:
            tailer_task.cancel()
            try:
                await tailer_task
            except asyncio.CancelledError:
                pass

    app.include_router(health_router)
    app.include_router(openai_router)
    app.include_router(traces_router)
    app.include_router(runs_router)
    app.include_router(subjects_router)
    app.include_router(llm_calls_router)
    app.include_router(correlations_router)
    app.include_router(raw_router)
    app.include_router(agent_events_router)
    app.include_router(constraints_router)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        repo = Repository.from_env()
        runs = repo.list_runs(100)
        session_ids = [r["session_id"] for r in runs if r.get("session_id") and r["session_id"] != "unknown"]
        stage_counts = repo.stage_counts_for_sessions(list({sid for sid in session_ids}))
        for r in runs:
            r["stage_counts"] = stage_counts.get(r.get("session_id"), {})
        constraints = repo.list_pinned_constraints()
        return templates.TemplateResponse(request, "index.html", {"runs": runs, "constraints": constraints})

    @app.get("/traces/{trace_id}", response_class=HTMLResponse)
    def trace_page(request: Request, trace_id: str):
        repo = Repository.from_env()
        llm_calls = repo.list_llm_calls_for_trace(trace_id)
        call_views = []
        for call in llm_calls:
            _, response_view = _load_call_payloads(call)
            call_views.append({"call": call, "response_view": response_view})
        run = repo.get_trace_run(trace_id)
        agent_events = repo.list_agent_events(trace_id)
        session_events: list[dict[str, object]] = []
        session_id = (run or {}).get("session_id") if run else None
        if session_id and session_id != "unknown":
            session_events = repo.list_agent_events_by_session(session_id)
        from app.agent_event_views import enrich_events
        from app.stage_diff import compute_stage_diff
        agent_events = enrich_events(agent_events)
        session_events_raw = list(session_events)
        session_events = enrich_events(session_events)

        # Compute provider-adapter diff per model-call trace_id (where both
        # context and before_provider_payload exist for the same trace_id).
        diffs_by_trace: dict[str, dict] = {}
        from collections import defaultdict
        by_trace: dict[str, dict[str, dict]] = defaultdict(dict)
        for e in session_events:
            by_trace[e["trace_id"]][e["stage"]] = e
        for tid, stages in by_trace.items():
            ctx_ev = stages.get("context")
            pp_ev = stages.get("before_provider_payload")
            if ctx_ev and pp_ev:
                diff = compute_stage_diff(ctx_ev.get("payload"), pp_ev.get("payload"))
                if diff:
                    diffs_by_trace[tid] = diff
        return templates.TemplateResponse(request, "trace.html", {
            "trace_id": trace_id,
            "run": run,
            "events": repo.list_events(trace_id),
            "llm_calls": llm_calls,
            "call_views": call_views,
            "correlations": repo.list_external_ids_for_trace(trace_id),
            "payload_mode": current_payload_mode(),
            "agent_events": agent_events,
            "session_events": session_events,
            "session_id": session_id,
            "stage_diffs": diffs_by_trace,
        })

    @app.get("/llm-calls/{llm_call_id}", response_class=HTMLResponse)
    def llm_call_page(request: Request, llm_call_id: str):
        repo = Repository.from_env()
        call = repo.get_llm_call(llm_call_id)
        payloads = {}
        response_view = {"assistant_text": "", "reasoning_text": ""}
        if call:
            payloads, response_view = _load_call_payloads(call)
        return templates.TemplateResponse(
            request,
            "llm_call.html",
            {
                "call": call,
                "payloads": payloads,
                "response_view": response_view,
                "payload_mode": current_payload_mode(),
                "payload_label": payload_label(),
            },
        )

    return app


app = create_app()
