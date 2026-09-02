"""Repository over runs, reports, append-only action_audit, and raw_logs.

Thin by design: it moves rows, it does not judge. Every compliance decision has already
been made by `core/` before anything here is called.

Postgres-specific surface is confined to three things — `%s` placeholders, `ON CONFLICT`
upserts, and `datetime` values passed straight through rather than pre-formatted, since
the timestamp columns are `TIMESTAMPTZ` and the driver adapts in both directions. Run
timestamps are already tz-aware UTC before they arrive here, so the column type is a
tightening, not a conversion.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from app.core.models import Action, Report, Violation
from app.core.run import Budget, Run, RunStatus
from app.store.db import connect


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_dt(value: Any) -> Optional[datetime]:
    """TIMESTAMPTZ comes back as a datetime; tolerate a string for robustness."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _row_to_run(row: Mapping[str, Any]) -> Run:
    return Run(
        id=row["id"],
        tenant_id=row["tenant_id"],
        correlation_id=row["correlation_id"],
        idempotency_key=row["idempotency_key"],
        rulepack_version=row["rulepack_version"],
        status=RunStatus(row["status"]),
        budget=Budget.model_validate_json(row["budget_json"]),
        tokens_used=row["tokens_used"] or 0,
        cost_inr=row["cost_inr"] or 0.0,
        turns_used=row["turns_used"] or 0,
        started_at=_as_dt(row["started_at"]),
        ended_at=_as_dt(row["ended_at"]),
    )


# --------------------------------------------------------------------------
# runs
# --------------------------------------------------------------------------


def open_run(run: Run) -> Run:
    with connect() as conn:
        conn.execute(
            """INSERT INTO runs (id, tenant_id, correlation_id, idempotency_key,
                                 rulepack_version, status, budget_json, tokens_used,
                                 cost_inr, turns_used, started_at, ended_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                run.id, run.tenant_id, run.correlation_id, run.idempotency_key,
                run.rulepack_version, run.status.value, run.budget.model_dump_json(),
                run.tokens_used, run.cost_inr, run.turns_used,
                run.started_at, run.ended_at,
            ),
        )
    return run


def close_run(run: Run, status: RunStatus) -> Run:
    run.status = status
    run.ended_at = _now()
    with connect() as conn:
        conn.execute(
            """UPDATE runs SET status=%s, tokens_used=%s, cost_inr=%s, turns_used=%s,
                               ended_at=%s
               WHERE id=%s""",
            (
                status.value, run.tokens_used, run.cost_inr, run.turns_used,
                run.ended_at, run.id,
            ),
        )
    return run


def get_run(run_id: str, tenant_id: Optional[str] = None) -> Optional[Run]:
    sql, args = "SELECT * FROM runs WHERE id=%s", [run_id]
    if tenant_id is not None:
        sql, args = sql + " AND tenant_id=%s", args + [tenant_id]
    with connect() as conn:
        row = conn.execute(sql, tuple(args)).fetchone()
    return _row_to_run(row) if row else None


def find_run_by_idempotency_key(key: str, tenant_id: Optional[str] = None) -> Optional[Run]:
    """Tenant-scoped: otherwise one tenant's idempotency key could return another's run,
    which would hand over a whole report rather than merely leaking its existence."""
    sql, args = "SELECT * FROM runs WHERE idempotency_key=%s", [key]
    if tenant_id is not None:
        sql, args = sql + " AND tenant_id=%s", args + [tenant_id]
    with connect() as conn:
        row = conn.execute(sql, tuple(args)).fetchone()
    return _row_to_run(row) if row else None


# --------------------------------------------------------------------------
# reports
# --------------------------------------------------------------------------


def save_report(report: Report, run_id: str) -> Report:
    with connect() as conn:
        conn.execute(
            """INSERT INTO reports
               (id, run_id, created_at, rulepack_version, score, passed, failed, payload)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET
                 run_id=EXCLUDED.run_id,
                 created_at=EXCLUDED.created_at,
                 rulepack_version=EXCLUDED.rulepack_version,
                 score=EXCLUDED.score,
                 passed=EXCLUDED.passed,
                 failed=EXCLUDED.failed,
                 payload=EXCLUDED.payload""",
            (
                report.id, run_id, report.created_at, report.rulepack_version,
                report.score, report.passed, report.failed, report.model_dump_json(),
            ),
        )
    return report


def get_report(report_id: str, tenant_id: Optional[str] = None) -> Optional[Report]:
    """`reports` carries no tenant column; the owning run does, so scoping joins to it."""
    if tenant_id is None:
        sql, args = "SELECT payload FROM reports WHERE id=%s", (report_id,)
    else:
        sql, args = (
            "SELECT r.payload FROM reports r JOIN runs u ON r.run_id = u.id "
            "WHERE r.id=%s AND u.tenant_id=%s",
            (report_id, tenant_id),
        )
    with connect() as conn:
        row = conn.execute(sql, args).fetchone()
    return Report.model_validate_json(row["payload"]) if row else None


def get_report_for_run(run_id: str, tenant_id: Optional[str] = None) -> Optional[Report]:
    if tenant_id is None:
        sql, args = (
            "SELECT payload FROM reports WHERE run_id=%s ORDER BY created_at DESC LIMIT 1",
            (run_id,),
        )
    else:
        sql, args = (
            "SELECT r.payload FROM reports r JOIN runs u ON r.run_id = u.id "
            "WHERE r.run_id=%s AND u.tenant_id=%s ORDER BY r.created_at DESC LIMIT 1",
            (run_id, tenant_id),
        )
    with connect() as conn:
        row = conn.execute(sql, args).fetchone()
    return Report.model_validate_json(row["payload"]) if row else None


def list_reports(
    limit: int = 50, offset: int = 0, tenant_id: Optional[str] = None
) -> list[Report]:
    if tenant_id is None:
        sql, args = (
            "SELECT payload FROM reports ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (limit, offset),
        )
    else:
        sql, args = (
            "SELECT r.payload FROM reports r JOIN runs u ON r.run_id = u.id "
            "WHERE u.tenant_id=%s ORDER BY r.created_at DESC LIMIT %s OFFSET %s",
            (tenant_id, limit, offset),
        )
    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [Report.model_validate_json(r["payload"]) for r in rows]


def count_reports(tenant_id: Optional[str] = None) -> int:
    if tenant_id is None:
        sql, args = "SELECT COUNT(*) AS n FROM reports", None
    else:
        sql, args = (
            "SELECT COUNT(*) AS n FROM reports r JOIN runs u ON r.run_id = u.id "
            "WHERE u.tenant_id=%s",
            (tenant_id,),
        )
    with connect() as conn:
        return conn.execute(sql, args).fetchone()["n"]


# --------------------------------------------------------------------------
# action_audit (append-only)
# --------------------------------------------------------------------------


def append_audit(run_id: str, actions: list[Action], violations: list[Violation]) -> int:
    """One row per action, plus one row per violation beyond the first on that action."""
    by_action: dict[str, list[Violation]] = {}
    for v in violations:
        by_action.setdefault(v.action_id, []).append(v)

    now = _now()
    rows: list[tuple[Any, ...]] = []
    for a in actions:
        found = by_action.get(a.id, [])
        if not found:
            rows.append((run_id, a.id, a.type.value, "pass", None, None, now))
        else:
            rows.extend(
                (run_id, a.id, a.type.value, "fail", v.rule_id, v.clause, now)
                for v in found
            )

    with connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO action_audit
                   (run_id, action_id, action_type, verdict, rule_id, clause, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                rows,
            )
    return len(rows)


def get_audit(run_id: str, tenant_id: Optional[str] = None) -> list[dict[str, Any]]:
    if tenant_id is None:
        sql, args = "SELECT * FROM action_audit WHERE run_id=%s ORDER BY id", (run_id,)
    else:
        sql, args = (
            "SELECT a.* FROM action_audit a JOIN runs u ON a.run_id = u.id "
            "WHERE a.run_id=%s AND u.tenant_id=%s ORDER BY a.id",
            (run_id, tenant_id),
        )
    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# raw_logs
# --------------------------------------------------------------------------


def save_raw_log(run_id: str, fmt: str, content: Any) -> None:
    text = content if isinstance(content, str) else json.dumps(content, default=str)
    with connect() as conn:
        conn.execute(
            """INSERT INTO raw_logs (run_id, format, content) VALUES (%s,%s,%s)
               ON CONFLICT (run_id) DO UPDATE SET
                 format=EXCLUDED.format, content=EXCLUDED.content""",
            (run_id, fmt, text),
        )


def get_raw_log(run_id: str) -> Optional[dict[str, str]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM raw_logs WHERE run_id=%s", (run_id,)
        ).fetchone()
    return {"format": row["format"], "content": row["content"]} if row else None
