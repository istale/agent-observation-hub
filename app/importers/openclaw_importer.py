import argparse
import json
import time
from pathlib import Path

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
    args = parser.parse_args()
    repo = Repository.from_env()
    path = Path(args.path)
    with path.open(encoding="utf-8") as fh:
        while True:
            line = fh.readline()
            if line:
                ingest_line(repo, line)
            elif args.follow:
                time.sleep(0.5)
            else:
                break


if __name__ == "__main__":
    main()
