from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import get_settings


class RawStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "RawStore":
        return cls(get_settings().data_dir / "raw")

    def _trace_dir(self, trace_id: str) -> Path:
        day = datetime.now(UTC).date().isoformat()
        path = self.root / day / f"trace_{trace_id}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _ref_for(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _resolve(self, payload_ref: str) -> Path:
        candidate = (self.root / payload_ref).resolve()
        root = self.root.resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError("payload_ref escapes raw archive")
        return candidate

    def write_json(self, trace_id: str, filename: str, payload: Any) -> str:
        path = self._trace_dir(trace_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return self._ref_for(path)

    def append_jsonl(self, trace_id: str, filename: str, payload: Any) -> str:
        path = self._trace_dir(trace_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return self._ref_for(path)

    def read_text(self, payload_ref: str) -> str:
        return self._resolve(payload_ref).read_text(encoding="utf-8")

    def read(self, payload_ref: str) -> Any:
        return json.loads(self.read_text(payload_ref))

    def read_jsonl(self, payload_ref: str) -> list[Any]:
        text = self.read_text(payload_ref)
        return [json.loads(line) for line in text.splitlines() if line.strip()]
