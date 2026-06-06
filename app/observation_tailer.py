"""Background tailer that ingests agent events from Pi's JSONL output.

Watches `$AOH_OBSERVATION_DIR/**/*.jsonl` and inserts new lines into
the agent_events table. Tracks per-file byte offsets in a state file so
restarts don't re-ingest.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.storage.repositories import Repository

logger = logging.getLogger(__name__)

INLINE_MAX_BYTES = 4096
STATE_FILENAME = ".aoh_tail_state.json"


def _load_state(state_path: Path) -> dict[str, int]:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state_path: Path, state: dict[str, int]) -> None:
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(state_path)


def _store_payload(trace_id: str, event_seq: Any, stage: str, payload: Any) -> tuple[str | None, str | None]:
    """Same convention as app.api.agent_events._store_payload: ref is relative
    to data_dir/raw so /api/raw/{ref} resolves correctly."""
    if payload is None:
        return None, None
    encoded = json.dumps(payload, ensure_ascii=False)
    if len(encoded.encode("utf-8")) <= INLINE_MAX_BYTES:
        return encoded, None
    settings = get_settings()
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw_root = settings.data_dir / "raw"
    target_dir = raw_root / date / f"trace_{trace_id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    seq_part = f"_{event_seq}" if event_seq is not None else ""
    target = target_dir / f"agent_event{seq_part}_{stage}.json"
    target.write_text(encoded, encoding="utf-8")
    return None, str(target.relative_to(raw_root))


def _ingest_line(repo: Repository, raw: str) -> bool:
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return False
    trace_id = event.get("trace_id")
    stage = event.get("stage")
    if not trace_id or not stage:
        return False
    payload_inline, payload_ref = _store_payload(trace_id, event.get("event_seq"), stage, event.get("payload"))
    repo.insert_agent_event({
        "trace_id": trace_id,
        "session_id": event.get("session_id"),
        "event_seq": event.get("event_seq"),
        "stage": stage,
        "source_module": event.get("source_module"),
        "ts": event.get("ts") or datetime.now(timezone.utc).isoformat(),
        "payload_ref": payload_ref,
        "payload_inline": payload_inline,
    })
    return True


def _scan_once(observation_dir: Path, state: dict[str, int]) -> int:
    """Read new bytes from every .jsonl under observation_dir. Returns event count."""
    repo = Repository.from_env()
    ingested = 0
    for path in observation_dir.rglob("*.jsonl"):
        key = str(path)
        offset = state.get(key, 0)
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            continue
        if size < offset:
            offset = 0  # file was rotated/truncated
        if size == offset:
            continue
        with path.open("r", encoding="utf-8") as f:
            f.seek(offset)
            for line in f:
                if not line.endswith("\n"):
                    # partial line; stop here, retry next tick
                    break
                stripped = line.strip()
                if stripped and _ingest_line(repo, stripped):
                    ingested += 1
                offset += len(line.encode("utf-8"))
        state[key] = offset
    return ingested


async def run_tailer() -> None:
    settings = get_settings()
    observation_dir = settings.observation_dir
    observation_dir.mkdir(parents=True, exist_ok=True)
    state_path = observation_dir / STATE_FILENAME
    state = _load_state(state_path)
    interval = settings.observation_tail_interval
    logger.info("agent-event tailer started: dir=%s interval=%.2fs", observation_dir, interval)
    while True:
        try:
            count = _scan_once(observation_dir, state)
            if count:
                _save_state(state_path, state)
                logger.info("agent-event tailer ingested %d events", count)
        except asyncio.CancelledError:
            _save_state(state_path, state)
            raise
        except Exception:
            logger.exception("agent-event tailer scan failed")
        await asyncio.sleep(interval)
