from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.storage.db import db_connection


TERMINAL_STATUSES = {"ok", "error", "cancelled"}


@dataclass(frozen=True)
class BackfillSummary:
    finalized_ok: int = 0
    finalized_error: int = 0
    cancelled_stale_calls: int = 0
    cancelled_stale_runs: int = 0

    @property
    def changed(self) -> int:
        return self.finalized_ok + self.finalized_error + self.cancelled_stale_calls + self.cancelled_stale_runs


def backfill_running_runs(db_path: Path | None = None, *, stale_minutes: int = 60, apply: bool = False) -> BackfillSummary:
    now = datetime.now(UTC)
    stale_before = now - timedelta(minutes=stale_minutes)
    with db_connection(db_path) as conn:
        stale_calls = conn.execute(
            """
            SELECT llm_call_id
            FROM llm_calls
            WHERE status = 'running'
              AND ended_at IS NULL
              AND started_at < ?
            """,
            (stale_before.isoformat().replace("+00:00", "Z"),),
        ).fetchall()

        terminal_runs = conn.execute(
            """
            SELECT
              r.run_id,
              CASE
                WHEN SUM(CASE WHEN c.status = 'error' THEN 1 ELSE 0 END) > 0 THEN 'error'
                WHEN SUM(CASE WHEN c.status = 'cancelled' THEN 1 ELSE 0 END) > 0 THEN 'error'
                ELSE 'ok'
              END AS final_status,
              MAX(c.ended_at) AS final_ended_at
            FROM trace_runs r
            JOIN llm_calls c ON c.run_id = r.run_id
            WHERE r.status = 'running'
            GROUP BY r.run_id
            HAVING COUNT(*) > 0
               AND SUM(CASE WHEN c.status IN ('ok', 'error', 'cancelled') AND c.ended_at IS NOT NULL THEN 1 ELSE 0 END) = COUNT(*)
            """,
        ).fetchall()

        stale_runs = conn.execute(
            """
            SELECT r.run_id
            FROM trace_runs r
            LEFT JOIN llm_calls c ON c.run_id = r.run_id
            WHERE r.status = 'running'
              AND r.ended_at IS NULL
              AND r.started_at < ?
            GROUP BY r.run_id
            HAVING COUNT(c.llm_call_id) = 0
                OR SUM(CASE WHEN c.status = 'running' THEN 1 ELSE 0 END) > 0
            """,
            (stale_before.isoformat().replace("+00:00", "Z"),),
        ).fetchall()

        summary = BackfillSummary(
            finalized_ok=sum(1 for row in terminal_runs if row["final_status"] == "ok"),
            finalized_error=sum(1 for row in terminal_runs if row["final_status"] == "error"),
            cancelled_stale_calls=len(stale_calls),
            cancelled_stale_runs=len(stale_runs),
        )
        if not apply:
            return summary

        ended_at = now.isoformat().replace("+00:00", "Z")
        for row in stale_calls:
            conn.execute(
                """
                UPDATE llm_calls
                SET status = 'cancelled',
                    ended_at = COALESCE(ended_at, ?),
                    error_type = COALESCE(error_type, 'stale_running_call'),
                    error_message = COALESCE(error_message, 'Backfilled stale running call after maintenance timeout')
                WHERE llm_call_id = ?
                """,
                (ended_at, row["llm_call_id"]),
            )

        for row in terminal_runs:
            conn.execute(
                """
                UPDATE trace_runs
                SET status = ?,
                    ended_at = COALESCE(ended_at, ?),
                    failure_type = CASE WHEN ? = 'error' THEN COALESCE(failure_type, 'stale_or_failed_child_call') ELSE failure_type END
                WHERE run_id = ?
                """,
                (row["final_status"], row["final_ended_at"], row["final_status"], row["run_id"]),
            )

        for row in stale_runs:
            conn.execute(
                """
                UPDATE trace_runs
                SET status = 'error',
                    ended_at = COALESCE(ended_at, ?),
                    failure_type = COALESCE(failure_type, 'stale_running_run')
                WHERE run_id = ?
                  AND status = 'running'
                """,
                (ended_at, row["run_id"]),
            )
    return summary


def _format_summary(summary: BackfillSummary, *, apply: bool) -> str:
    mode = "applied" if apply else "dry-run"
    return (
        f"{mode}: finalized_ok={summary.finalized_ok} "
        f"finalized_error={summary.finalized_error} "
        f"cancelled_stale_calls={summary.cancelled_stale_calls} "
        f"cancelled_stale_runs={summary.cancelled_stale_runs} "
        f"changed={summary.changed}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill stale running trace_runs from llm_call state.")
    parser.add_argument("--db", type=Path, default=None, help="SQLite database path. Defaults to AOH_DATABASE_PATH.")
    parser.add_argument("--stale-minutes", type=int, default=60, help="Age threshold for cancelling stuck running rows.")
    parser.add_argument("--apply", action="store_true", help="Write updates. Omit for dry-run.")
    args = parser.parse_args(argv)

    summary = backfill_running_runs(args.db, stale_minutes=args.stale_minutes, apply=args.apply)
    print(_format_summary(summary, apply=args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
