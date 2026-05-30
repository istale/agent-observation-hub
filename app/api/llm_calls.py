from fastapi import APIRouter, HTTPException

from app.storage.repositories import Repository
from app.trace.raw_store import RawStore
from app.trace.redaction import redact

router = APIRouter()


@router.get("/api/llm-calls/{llm_call_id}")
def get_llm_call(llm_call_id: str) -> dict[str, object]:
    call = Repository.from_env().get_llm_call(llm_call_id)
    if not call:
        raise HTTPException(status_code=404, detail="llm call not found")
    store = RawStore.from_env()
    payloads = {}
    for key in ("request_ref", "response_ref"):
        if call.get(key):
            payloads[key.removesuffix("_ref")] = redact(store.read(call[key]))
    if call.get("response_chunks_ref"):
        payloads["response_chunks"] = redact(store.read_jsonl(call["response_chunks_ref"]))
    return {"llm_call": call, "payloads": payloads}
