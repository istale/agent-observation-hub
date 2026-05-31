import argparse
import time
from pathlib import Path
from typing import Any

from app.importers.agent_events.normalizer import parse_line
from app.importers.agent_events.roots import load_roots_config, paths_for_source
from app.importers.agent_events.writer import write_event
from app.storage.repositories import Repository


def _read_paths(paths: list[Path], *, follow: bool = False):
    for path in paths:
        with path.open(encoding="utf-8") as fh:
            while True:
                line = fh.readline()
                if line:
                    yield line
                elif follow:
                    time.sleep(0.5)
                else:
                    break


def run_import(
    *,
    source: str,
    paths: list[str | Path] | None = None,
    roots_config: str | Path | None = None,
    user_hash: str | None = None,
    follow: bool = False,
    dry_run: bool = False,
    repo: Repository | None = None,
) -> dict[str, Any]:
    repo = repo or Repository.from_env()
    resolved_paths = [Path(path).expanduser() for path in (paths or [])]
    if roots_config:
        config = load_roots_config(roots_config)
        resolved_paths.extend(paths_for_source(config, source=source, user_hash=user_hash))

    parsed = 0
    written = 0
    events = []
    for line in _read_paths(resolved_paths, follow=follow):
        event = parse_line(line, source=source, user_hash=user_hash)
        parsed += 1
        if dry_run:
            events.append(event.__dict__)
        else:
            write_event(repo, event)
            written += 1
    return {"parsed": parsed, "written": written, "events": events}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, choices=["hermes", "openclaw"])
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--roots-config")
    parser.add_argument("--user-hash")
    parser.add_argument("--follow", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run_import(
        source=args.source,
        paths=args.path,
        roots_config=args.roots_config,
        user_hash=args.user_hash,
        follow=args.follow,
        dry_run=args.dry_run,
    )
    print(result)


if __name__ == "__main__":
    main()
