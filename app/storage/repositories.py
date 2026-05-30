from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.storage.db import db_connection, init_db


def _row(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class Repository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        init_db(self.db_path)

    @classmethod
    def from_env(cls) -> "Repository":
        return cls(get_settings().database_path)

    def upsert_run(self, data: dict[str, Any]) -> None:
        fields = [
            "run_id", "trace_id", "tenant_id", "user_id", "user_hash", "agent_id", "session_id",
            "channel", "channel_id", "conversation_id", "trigger_type", "started_at", "ended_at",
            "status", "input_summary", "output_summary", "failure_type",
        ]
        values = {field: data.get(field) for field in fields}
        values["status"] = values.get("status") or "running"
        cols = ", ".join(fields)
        placeholders = ", ".join(f":{field}" for field in fields)
        updates = ", ".join(f"{field}=excluded.{field}" for field in fields if field != "run_id")
        with db_connection(self.db_path) as conn:
            conn.execute(f"INSERT INTO trace_runs ({cols}) VALUES ({placeholders}) ON CONFLICT(run_id) DO UPDATE SET {updates}", values)

    def insert_event(self, data: dict[str, Any]) -> None:
        fields = [
            "event_id", "trace_id", "run_id", "parent_event_id", "event_type", "source", "timestamp",
            "status", "severity", "payload_json", "payload_ref", "redaction_level",
        ]
        values = {field: data.get(field) for field in fields}
        values["status"] = values.get("status") or "ok"
        values["severity"] = values.get("severity") or "info"
        values["redaction_level"] = values.get("redaction_level") or "redacted"
        if isinstance(values.get("payload_json"), (dict, list)):
            values["payload_json"] = json.dumps(values["payload_json"], ensure_ascii=False)
        with db_connection(self.db_path) as conn:
            conn.execute(
                f"INSERT INTO trace_events ({', '.join(fields)}) VALUES ({', '.join(':' + f for f in fields)})",
                values,
            )

    def insert_llm_call(self, data: dict[str, Any]) -> None:
        fields = [
            "llm_call_id", "trace_id", "run_id", "tenant_id", "user_id", "user_hash", "agent_id",
            "session_id", "channel", "conversation_id", "provider", "upstream_base_url", "model",
            "endpoint", "is_stream", "started_at", "ended_at", "latency_ms", "status", "http_status",
            "error_type", "error_message", "input_tokens", "output_tokens", "total_tokens",
            "request_ref", "response_ref", "response_chunks_ref", "redaction_level",
        ]
        values = {field: data.get(field) for field in fields}
        values["is_stream"] = 1 if values.get("is_stream") else 0
        values["status"] = values.get("status") or "running"
        values["redaction_level"] = values.get("redaction_level") or "raw_local"
        with db_connection(self.db_path) as conn:
            conn.execute(
                f"INSERT INTO llm_calls ({', '.join(fields)}) VALUES ({', '.join(':' + f for f in fields)})",
                values,
            )

    def update_llm_call(self, llm_call_id: str, data: dict[str, Any]) -> None:
        if not data:
            return
        assignments = ", ".join(f"{key}=:{key}" for key in data)
        values = dict(data)
        values["llm_call_id"] = llm_call_id
        with db_connection(self.db_path) as conn:
            conn.execute(f"UPDATE llm_calls SET {assignments} WHERE llm_call_id=:llm_call_id", values)

    def update_run(self, run_id: str, data: dict[str, Any]) -> None:
        values = {key: value for key, value in data.items() if value is not None}
        if not values:
            return
        assignments = ", ".join(f"{key}=:{key}" for key in values)
        values["run_id"] = run_id
        with db_connection(self.db_path) as conn:
            conn.execute(f"UPDATE trace_runs SET {assignments} WHERE run_id=:run_id", values)

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with db_connection(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM trace_runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with db_connection(self.db_path) as conn:
            return _row(conn.execute("SELECT * FROM trace_runs WHERE run_id = ?", (run_id,)).fetchone())

    def get_trace_run(self, trace_id: str) -> dict[str, Any] | None:
        with db_connection(self.db_path) as conn:
            return _row(conn.execute("SELECT * FROM trace_runs WHERE trace_id = ? ORDER BY started_at DESC LIMIT 1", (trace_id,)).fetchone())

    def list_traces(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.list_runs(limit)

    def list_events(self, trace_id: str) -> list[dict[str, Any]]:
        with db_connection(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM trace_events WHERE trace_id = ? ORDER BY timestamp ASC", (trace_id,)).fetchall()
        return [dict(row) for row in rows]

    def list_llm_calls_for_trace(self, trace_id: str) -> list[dict[str, Any]]:
        with db_connection(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM llm_calls WHERE trace_id = ? ORDER BY started_at ASC", (trace_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_llm_call(self, llm_call_id: str) -> dict[str, Any] | None:
        with db_connection(self.db_path) as conn:
            return _row(conn.execute("SELECT * FROM llm_calls WHERE llm_call_id = ?", (llm_call_id,)).fetchone())

    def insert_external_id(self, data: dict[str, Any]) -> None:
        fields = ["trace_id", "run_id", "llm_call_id", "source", "key", "value", "value_hash"]
        values = {field: data.get(field) for field in fields}
        values["value"] = str(values["value"])
        values["value_hash"] = values.get("value_hash") or hashlib.sha256(values["value"].encode("utf-8")).hexdigest()
        with db_connection(self.db_path) as conn:
            conn.execute(
                f"INSERT OR IGNORE INTO external_ids ({', '.join(fields)}) VALUES ({', '.join(':' + f for f in fields)})",
                values,
            )

    def list_external_ids_for_trace(self, trace_id: str) -> list[dict[str, Any]]:
        with db_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM external_ids WHERE trace_id = ? ORDER BY source, key, value",
                (trace_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def find_external_ids(self, *, source: str | None = None, key: str | None = None, value: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        clauses = []
        values: list[Any] = []
        if source:
            clauses.append("source = ?")
            values.append(source)
        if key:
            clauses.append("key = ?")
            values.append(key)
        if value:
            clauses.append("value = ?")
            values.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(limit)
        with db_connection(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM external_ids {where} ORDER BY created_at DESC LIMIT ?",
                values,
            ).fetchall()
        return [dict(row) for row in rows]
