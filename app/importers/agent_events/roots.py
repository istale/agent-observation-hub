import json
from pathlib import Path
from typing import Any


def load_roots_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def paths_for_source(config: dict[str, Any], *, source: str, user_hash: str | None = None) -> list[Path]:
    roots_key = f"{source}_roots"
    paths: list[Path] = []
    for item in config.get(roots_key, []):
        if user_hash and item.get("user_hash") != user_hash:
            continue
        root = Path(item["path"]).expanduser()
        if source == "hermes":
            paths.extend(sorted((root / "logs").glob("*.log")))
        elif source == "openclaw":
            paths.extend(sorted(root.glob("agents/*/sessions/*.jsonl")))
    return paths
