"""Durable state — 02-system-design.md §B.4.

State lives *outside* the process. A demo keeps reports in memory; this does not, which
is what makes replay, idempotency and the audit trail real rather than claimed.

**Postgres.** The MVP ran on SQLite and the seam held: this module and the placeholder
style in `repository.py` are the only things that changed, and nothing above `store/`
learned about it. The move was forced by deployment, not by scale — a container host's
filesystem is ephemeral, so a SQLite file is erased on every redeploy, and an audit trail
that does not survive a deploy is not an audit trail.

Two deliberate choices worth stating:

* **A pool, not a connection per call.** Every repository function opens a connection.
  On SQLite that was free; against a network Postgres it is a TLS round trip, and a
  single verification run makes five or more. The pool makes the seam's cost invisible.
* **`payload` and `budget_json` stay `TEXT`, not `JSONB`.** JSONB normalises key order
  and drops duplicate keys, so the bytes read back would not be the bytes the membrane
  validated. For an artifact whose purpose is to be auditable, byte-fidelity beats
  queryability.

`action_audit` is append-only *by trigger*, not merely by policy. Invariant I10 claims the
audit trail is a compliance artifact — a claim worth nothing if any code path can quietly
rewrite it, so the database refuses UPDATE and DELETE outright.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  idempotency_key TEXT UNIQUE,
  rulepack_version TEXT NOT NULL,
  status TEXT NOT NULL,
  budget_json TEXT NOT NULL,
  tokens_used BIGINT DEFAULT 0,
  cost_inr DOUBLE PRECISION DEFAULT 0,
  turns_used BIGINT DEFAULT 0,
  started_at TIMESTAMPTZ NOT NULL,
  ended_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY,
  run_id TEXT REFERENCES runs(id),
  created_at TIMESTAMPTZ NOT NULL,
  rulepack_version TEXT NOT NULL,
  score DOUBLE PRECISION,
  passed INTEGER,
  failed INTEGER,
  payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_audit (
  id BIGSERIAL PRIMARY KEY,
  run_id TEXT REFERENCES runs(id),
  action_id TEXT NOT NULL,
  action_type TEXT NOT NULL,
  verdict TEXT NOT NULL,
  rule_id TEXT,
  clause TEXT,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_logs (
  run_id TEXT PRIMARY KEY REFERENCES runs(id),
  format TEXT NOT NULL,
  content TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_run ON action_audit(run_id);

-- Invariant I10: the audit trail is append-only. Enforced here, not by convention.
-- Postgres has no RAISE(ABORT) and no CREATE TRIGGER IF NOT EXISTS, so this is the
-- plpgsql equivalent of the two SQLite triggers it replaces: same guarantee, and the
-- exception message is unchanged so the assertion in the test suite still reads the same.
CREATE OR REPLACE FUNCTION action_audit_append_only() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
  RAISE EXCEPTION 'action_audit is append-only';
END;
$fn$;

DROP TRIGGER IF EXISTS action_audit_no_update ON action_audit;
CREATE TRIGGER action_audit_no_update
BEFORE UPDATE ON action_audit
FOR EACH ROW EXECUTE FUNCTION action_audit_append_only();

DROP TRIGGER IF EXISTS action_audit_no_delete ON action_audit;
CREATE TRIGGER action_audit_no_delete
BEFORE DELETE ON action_audit
FOR EACH ROW EXECUTE FUNCTION action_audit_append_only();
"""

_POOL: Optional[ConnectionPool] = None


def dsn(url: str | None = None) -> str:
    """Validate and return the Postgres DSN.

    The error is deliberately loud: a stale `sqlite:///` URL in a `.env` would otherwise
    fail much later and much more confusingly.
    """
    url = url or settings.DATABASE_URL
    if not url.startswith(("postgres://", "postgresql://")):
        raise ValueError(
            f"the store requires a Postgres URL, got {url!r}. "
            "Set DATABASE_URL=postgresql://... (Neon: use the -pooler host and "
            "?sslmode=require)."
        )
    return url


def _configure(conn: psycopg.Connection) -> None:
    """Runs once per pooled connection, not per checkout.

    The commit is required, not cosmetic: psycopg's pool discards any connection a
    configure callback leaves in a transaction. `SET` without `LOCAL` is session-scoped,
    so the search_path survives the commit and applies to every later checkout.
    """
    conn.execute(f'SET search_path TO "{settings.DB_SCHEMA}"')
    conn.commit()


def pool() -> ConnectionPool:
    global _POOL
    if _POOL is None:
        _POOL = ConnectionPool(
            conninfo=dsn(),
            min_size=1,
            max_size=settings.DB_POOL_MAX,
            kwargs={"row_factory": dict_row},
            configure=_configure,
            open=True,
        )
    return _POOL


def reset_pool() -> None:
    """Drop the pool so the next call rebuilds it — used when settings change."""
    global _POOL
    if _POOL is not None:
        _POOL.close()
        _POOL = None


@contextmanager
def connect(url: str | None = None) -> Iterator[psycopg.Connection]:
    """Commits on clean exit, rolls back on exception — same contract as before."""
    with pool().connection() as conn:
        yield conn


def init_db(url: str | None = None) -> None:
    """Idempotent. Called on FastAPI startup.

    Both statements go through the pool. `CREATE SCHEMA` names its target explicitly and
    so does not depend on search_path resolving, which lets it run on a connection whose
    search_path points at the schema it is about to create. Doing this on a separate
    connection instead costs a full TLS handshake every call, and the test suite calls
    this between tests.
    """
    with connect() as conn:
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{settings.DB_SCHEMA}"')
        conn.execute(SCHEMA)
