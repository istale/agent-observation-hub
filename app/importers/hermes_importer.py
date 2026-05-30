from app.importers.openclaw_importer import ingest_line
from app.storage.repositories import Repository


def main() -> None:
    import argparse
    import time
    from pathlib import Path

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
                ingest_line(repo, line, source="hermes")
            elif args.follow:
                time.sleep(0.5)
            else:
                break


if __name__ == "__main__":
    main()
