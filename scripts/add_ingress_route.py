#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from app.storage.repositories import Repository


def main() -> int:
    parser = argparse.ArgumentParser(description="Add or replace an Agent Observation Hub ingress route mapping.")
    parser.add_argument("--db", type=Path, default=None, help="SQLite DB path. Defaults to AOH_DATABASE_PATH.")
    parser.add_argument("--host", dest="listen_host", default="127.0.0.1")
    parser.add_argument("--port", dest="listen_port", type=int, required=True)
    parser.add_argument("--path-prefix", default="/v1")
    parser.add_argument("--tenant-id")
    parser.add_argument("--user-hash")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--note")
    parser.add_argument("--disabled", action="store_true")
    args = parser.parse_args()

    repo = Repository(args.db) if args.db else Repository.from_env()
    route = repo.insert_ingress_route({
        "listen_host": args.listen_host,
        "listen_port": args.listen_port,
        "path_prefix": args.path_prefix,
        "tenant_id": args.tenant_id,
        "user_hash": args.user_hash,
        "agent_id": args.agent_id,
        "channel": args.channel,
        "note": args.note,
        "enabled": 0 if args.disabled else 1,
    })
    print(
        f"route id={route['id']} host={route['listen_host']} port={route['listen_port']} "
        f"path={route['path_prefix']} agent={route['agent_id']} channel={route['channel']} "
        f"user_hash={route['user_hash']} enabled={route['enabled']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
