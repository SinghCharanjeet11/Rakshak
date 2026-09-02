import os
from pathlib import Path

# Must happen before any `app.*` import: app.config builds a cached Settings singleton at
# import time, and the store must never touch real rows.
#
# Tests run against Postgres — the same engine that ships — because invariant I10's
# append-only guarantee is enforced by a database trigger, and a trigger tested on a
# different engine than the one deployed is not tested at all. Isolation comes from a
# dedicated schema rather than a separate database, so no branch management is required;
# set TEST_DATABASE_URL to point at a throwaway Neon branch instead if you prefer.
_TEST_SCHEMA = os.environ.get("TEST_DB_SCHEMA", "rakshak_test")
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["DB_SCHEMA"] = _TEST_SCHEMA
os.environ["OPENAI_API_KEY"] = ""  # no test may reach a model provider
os.environ["ACTIVE_RULEPACK"] = "2026.04.21-1"

# The session fixture below DROPs this schema. Refusing to run against `public` is the
# difference between a test suite and an outage.
if _TEST_SCHEMA == "public":
    raise RuntimeError(
        "refusing to run the test suite against the `public` schema — it is dropped "
        "between sessions. Unset TEST_DB_SCHEMA or set it to a throwaway name."
    )

import json  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402

from app.core.models import Action  # noqa: E402
from app.core.rules_loader import RulePack, load_pack  # noqa: E402

SEED_DIR = Path(__file__).resolve().parent.parent / "app" / "seed"
IST = timezone(timedelta(hours=5, minutes=30))


def load_seed(name: str) -> list[Action]:
    raw = json.loads((SEED_DIR / name).read_text(encoding="utf-8"))
    return [Action.model_validate(x) for x in raw]


def seed_raw(name: str) -> Any:
    return json.loads((SEED_DIR / name).read_text(encoding="utf-8"))


def seed_text(name: str) -> str:
    return (SEED_DIR / name).read_text(encoding="utf-8")


def _drop_test_schema() -> None:
    import psycopg

    from app.store.db import dsn, reset_pool

    reset_pool()
    with psycopg.connect(dsn()) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{_TEST_SCHEMA}" CASCADE')
        conn.commit()


@pytest.fixture(scope="session", autouse=True)
def _fresh_database():
    from app.store.db import init_db

    _drop_test_schema()
    init_db()
    yield
    _drop_test_schema()


@pytest.fixture
def clean_db():
    """Wipe rows between tests that care about counts or idempotency collisions."""
    from app.store.db import connect, init_db

    with connect() as conn:
        conn.execute("DELETE FROM raw_logs")
        conn.execute("DELETE FROM reports")
        # action_audit is append-only by trigger; dropping the table is the only way
        # to reset it, and having to do this in a test is the proof the trigger works.
        conn.execute("DROP TABLE IF EXISTS action_audit CASCADE")
        conn.execute("DELETE FROM runs")

    init_db()
    yield


@pytest.fixture(scope="session")
def pack() -> RulePack:
    return load_pack("2026.04.21-1")


@pytest.fixture(scope="session")
def clean_actions() -> list[Action]:
    return load_seed("clean_actions.json")


@pytest.fixture(scope="session")
def violating_actions() -> list[Action]:
    return load_seed("violating_actions.json")


def make_action(**kwargs: Any) -> Action:
    """Minimal valid Action; override only the fields a test is actually about."""
    base: dict[str, Any] = {
        "id": "a_test",
        "type": "debit",
        "timestamp": datetime(2026, 8, 20, 12, 0, tzinfo=IST),
    }
    base.update(kwargs)
    return Action.model_validate(base)
