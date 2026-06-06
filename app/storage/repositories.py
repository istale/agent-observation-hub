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
            "status", "input_summary", "output_summary", "failure_type", "identity_source",
        ]
        values = {field: data.get(field) for field in fields}
        values["status"] = values.get("status") or "running"
        values["identity_source"] = values.get("identity_source") or "unknown"
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
            "request_ref", "response_ref", "response_chunks_ref", "redaction_level", "identity_source",
        ]
        values = {field: data.get(field) for field in fields}
        values["is_stream"] = 1 if values.get("is_stream") else 0
        values["status"] = values.get("status") or "running"
        values["redaction_level"] = values.get("redaction_level") or "raw_local"
        values["identity_source"] = values.get("identity_source") or "unknown"
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

    def list_observed_users(self) -> list[dict[str, Any]]:
        with db_connection(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                  user_hash,
                  COUNT(*) AS trace_count,
                  COUNT(DISTINCT agent_id) AS agent_count,
                  MIN(started_at) AS first_seen,
                  MAX(started_at) AS last_seen
                FROM trace_runs
                WHERE user_hash IS NOT NULL
                GROUP BY user_hash
                ORDER BY last_seen DESC
                """
            ).fetchall()
            users = []
            for row in rows:
                item = dict(row)
                channels = conn.execute(
                    """
                    SELECT DISTINCT channel
                    FROM trace_runs
                    WHERE user_hash = ?
                      AND channel IS NOT NULL
                    ORDER BY channel
                    """,
                    (item["user_hash"],),
                ).fetchall()
                item["channels"] = [channel_row["channel"] for channel_row in channels]
                users.append(item)
        return users

    def list_user_traces(
        self,
        user_hash: str,
        *,
        limit: int = 50,
        days: int | None = None,
        agent_id: str | None = None,
        channel: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["r.user_hash = ?"]
        values: list[Any] = [user_hash]
        if agent_id:
            clauses.append("r.agent_id = ?")
            values.append(agent_id)
        if channel:
            clauses.append("r.channel = ?")
            values.append(channel)
        if status:
            clauses.append("r.status = ?")
            values.append(status)
        if days is not None:
            clauses.append("r.started_at >= datetime('now', ?)")
            values.append(f"-{days} days")
        values.append(limit)
        where = " AND ".join(clauses)
        with db_connection(self.db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT
                  r.trace_id,
                  r.run_id,
                  r.tenant_id,
                  r.user_hash,
                  r.agent_id,
                  r.channel,
                  r.status,
                  r.started_at,
                  r.ended_at,
                  r.identity_source,
                  COUNT(l.llm_call_id) AS llm_call_count,
                  COALESCE(SUM(l.total_tokens), 0) AS total_tokens,
                  MAX(l.latency_ms) AS max_latency_ms
                FROM trace_runs r
                LEFT JOIN llm_calls l ON l.trace_id = r.trace_id
                WHERE {where}
                GROUP BY r.trace_id, r.run_id
                ORDER BY r.started_at DESC
                LIMIT ?
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_user_agents(self, user_hash: str) -> list[dict[str, Any]]:
        with db_connection(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                  agent_id,
                  channel,
                  COUNT(*) AS trace_count,
                  MAX(started_at) AS last_seen
                FROM trace_runs
                WHERE user_hash = ?
                GROUP BY agent_id, channel
                ORDER BY last_seen DESC
                """,
                (user_hash,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_events(self, trace_id: str) -> list[dict[str, Any]]:
        with db_connection(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM trace_events WHERE trace_id = ? ORDER BY timestamp ASC", (trace_id,)).fetchall()
        return [dict(row) for row in rows]

    def list_llm_calls_for_trace(self, trace_id: str) -> list[dict[str, Any]]:
        with db_connection(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM llm_calls WHERE trace_id = ? ORDER BY started_at ASC", (trace_id,)).fetchall()
        return [dict(row) for row in rows]

    def insert_agent_event(self, data: dict[str, Any]) -> int:
        fields = ["trace_id", "session_id", "event_seq", "stage", "source_module", "ts", "payload_ref", "payload_inline"]
        values = {field: data.get(field) for field in fields}
        if isinstance(values.get("payload_inline"), (dict, list)):
            values["payload_inline"] = json.dumps(values["payload_inline"], ensure_ascii=False)
        with db_connection(self.db_path) as conn:
            cur = conn.execute(
                f"INSERT INTO agent_events ({', '.join(fields)}) VALUES ({', '.join(':' + f for f in fields)})",
                values,
            )
            return int(cur.lastrowid or 0)

    def list_agent_events(self, trace_id: str) -> list[dict[str, Any]]:
        with db_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM agent_events WHERE trace_id = ? ORDER BY event_seq ASC, id ASC",
                (trace_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def stage_counts_for_sessions(self, session_ids: list[str]) -> dict[str, dict[str, int]]:
        """Return {session_id: {stage: count}} for the given sessions in one query."""
        result: dict[str, dict[str, int]] = {sid: {} for sid in session_ids}
        if not session_ids:
            return result
        placeholders = ",".join("?" for _ in session_ids)
        with db_connection(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT session_id, stage, COUNT(*) AS c FROM agent_events "
                f"WHERE session_id IN ({placeholders}) GROUP BY session_id, stage",
                session_ids,
            ).fetchall()
        for row in rows:
            sid = row["session_id"]
            if sid not in result:
                result[sid] = {}
            result[sid][row["stage"]] = int(row["c"])
        return result

    def insert_pinned_constraint(self, data: dict[str, Any]) -> None:
        fields = ["id", "text", "scope"]
        values = {field: data.get(field) for field in fields}
        values["scope"] = values.get("scope") or "global"
        with db_connection(self.db_path) as conn:
            conn.execute(
                f"INSERT INTO pinned_constraints ({', '.join(fields)}) VALUES ({', '.join(':' + f for f in fields)})",
                values,
            )

    def list_pinned_constraints(self, scope: str | None = None) -> list[dict[str, Any]]:
        with db_connection(self.db_path) as conn:
            if scope:
                rows = conn.execute(
                    "SELECT * FROM pinned_constraints WHERE scope = ? ORDER BY created_at ASC",
                    (scope,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM pinned_constraints ORDER BY scope ASC, created_at ASC"
                ).fetchall()
        return [dict(row) for row in rows]

    def delete_pinned_constraint(self, constraint_id: str) -> int:
        with db_connection(self.db_path) as conn:
            cur = conn.execute("DELETE FROM pinned_constraints WHERE id = ?", (constraint_id,))
            return int(cur.rowcount or 0)

    def list_agent_events_by_session(self, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with db_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM agent_events WHERE session_id = ? ORDER BY ts ASC, id ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
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

    def insert_ingress_route(self, data: dict[str, Any]) -> dict[str, Any]:
        fields = [
            "listen_host", "listen_port", "path_prefix", "tenant_id", "user_id", "user_hash",
            "agent_id", "session_id", "channel", "channel_id", "conversation_id", "source",
            "note", "enabled",
        ]
        values = {field: data.get(field) for field in fields}
        values["source"] = values.get("source") or "ingress_route"
        values["enabled"] = 1 if values.get("enabled") is None else (1 if values.get("enabled") else 0)
        with db_connection(self.db_path) as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO ingress_routes ({', '.join(fields)}) VALUES ({', '.join(':' + f for f in fields)})",
                values,
            )
            route_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            return dict(conn.execute("SELECT * FROM ingress_routes WHERE id = ?", (route_id,)).fetchone())

    def list_ingress_routes(self, *, enabled: int | None = None) -> list[dict[str, Any]]:
        where = ""
        values: list[Any] = []
        if enabled is not None:
            where = "WHERE enabled = ?"
            values.append(enabled)
        with db_connection(self.db_path) as conn:
            rows = conn.execute(f"SELECT * FROM ingress_routes {where} ORDER BY listen_port, path_prefix", values).fetchall()
        return [dict(row) for row in rows]

    def find_ingress_route(self, *, listen_host: str | None, listen_port: int | None, path: str) -> dict[str, Any] | None:
        with db_connection(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM ingress_routes
                WHERE enabled = 1
                  AND (listen_host IS NULL OR listen_host = ?)
                  AND (listen_port IS NULL OR listen_port = ?)
                ORDER BY LENGTH(COALESCE(path_prefix, '')) DESC
                """,
                (listen_host, listen_port),
            ).fetchall()
        for row in rows:
            route = dict(row)
            prefix = route.get("path_prefix")
            if not prefix or path.startswith(prefix):
                return route
        return None
