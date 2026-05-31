from pathlib import Path

from app.importers.agent_events.cli import run_import


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    parser.add_argument("--follow", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--user-hash")
    args = parser.parse_args()
    run_import(
        source="hermes",
        paths=[Path(args.path)],
        follow=args.follow,
        dry_run=args.dry_run,
        user_hash=args.user_hash,
    )


if __name__ == "__main__":
    main()
