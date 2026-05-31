import argparse
import json
import time
from pathlib import Path

from app.importers.agent_events.cli import run_import
from app.storage.repositories import Repository
from app.trace.events import utc_now_iso
from app.trace.ids import new_event_id, new_run_id, new_trace_id


def ingest_line(repo: Repository, line: str, source: str = "openclaw") -> None:
    trace_id = new_trace_id()
    run_id = new_run_id()
    repo.upsert_run({"run_id": run_id, "trace_id": trace_id, "started_at": utc_now_iso(), "status": "external"})
    try:
        payload = json.loads(line)
        event_type = payload.get("event_type", "external_log") if isinstance(payload, dict) else "external_log"
    except json.JSONDecodeError:
        payload = {"message": line.rstrip("\n")}
        event_type = "external_log"
    repo.insert_event({"event_id": new_event_id(), "trace_id": trace_id, "run_id": run_id, "event_type": event_type, "source": source, "timestamp": utc_now_iso(), "payload_json": payload})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    parser.add_argument("--follow", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--user-hash")
    args = parser.parse_args()
    run_import(
        source="openclaw",
        paths=[Path(args.path)],
        follow=args.follow,
        dry_run=args.dry_run,
        user_hash=args.user_hash,
    )


if __name__ == "__main__":
    main()
