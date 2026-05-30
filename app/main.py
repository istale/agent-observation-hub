from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.health import router as health_router
from app.api.llm_calls import router as llm_calls_router
from app.api.raw import router as raw_router
from app.api.runs import router as runs_router
from app.api.traces import router as traces_router
from app.gateway.openai_proxy import router as openai_router
from app.logging_config import configure_logging
from app.storage.db import init_db
from app.storage.repositories import Repository
from app.trace.raw_store import RawStore
from app.trace.redaction import redact
from app.ui.formatters import llm_response_view, taipei_time


templates = Jinja2Templates(directory="app/ui/templates")
templates.env.filters["taipei_time"] = taipei_time


def create_app() -> FastAPI:
    configure_logging()
    init_db()
    app = FastAPI(title="Agent Observation Hub")
    app.mount("/static", StaticFiles(directory="app/ui/static"), name="static")
    app.include_router(health_router)
    app.include_router(openai_router)
    app.include_router(traces_router)
    app.include_router(runs_router)
    app.include_router(llm_calls_router)
    app.include_router(raw_router)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        runs = Repository.from_env().list_runs(100)
        return templates.TemplateResponse(request, "index.html", {"runs": runs})

    @app.get("/traces/{trace_id}", response_class=HTMLResponse)
    def trace_page(request: Request, trace_id: str):
        repo = Repository.from_env()
        return templates.TemplateResponse(request, "trace.html", {
            "trace_id": trace_id,
            "run": repo.get_trace_run(trace_id),
            "events": repo.list_events(trace_id),
            "llm_calls": repo.list_llm_calls_for_trace(trace_id),
        })

    @app.get("/llm-calls/{llm_call_id}", response_class=HTMLResponse)
    def llm_call_page(request: Request, llm_call_id: str):
        repo = Repository.from_env()
        call = repo.get_llm_call(llm_call_id)
        payloads = {}
        response_view = {"assistant_text": "", "reasoning_text": ""}
        if call:
            store = RawStore.from_env()
            for key in ("request_ref", "response_ref"):
                if call.get(key):
                    payloads[key.removesuffix("_ref")] = redact(store.read(call[key]))
            if call.get("response_chunks_ref"):
                payloads["chunks"] = redact(store.read_jsonl(call["response_chunks_ref"]))
            response_view = llm_response_view(payloads.get("response"), payloads.get("chunks"))
        return templates.TemplateResponse(
            request,
            "llm_call.html",
            {"call": call, "payloads": payloads, "response_view": response_view},
        )

    return app


app = create_app()
