"""FastAPI entrypoint.

Startup does two things that must happen before the first request: load and *validate*
the rule-pack, and ensure the database schema exists. A malformed pack fails startup
loudly rather than at verification time — a compliance tool that boots with rules it
could not parse is worse than one that refuses to boot.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_health, routes_reports, routes_rules, routes_runs, routes_verify
from app.config import settings
from app.core.rules_loader import RulePackError
from app.orchestration.orchestrator import get_pack
from app.store.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
)
log = logging.getLogger("rakshak")

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    try:
        pack = get_pack()
    except RulePackError:
        log.exception("rule-pack failed to load — refusing to serve")
        raise

    log.info(
        "rakshak up · rulepack=%s · %d rules · %d exemptions · llm=%s",
        pack.version, len(pack.rules), len(pack.exemptions), settings.llm_enabled,
    )
    if unverified := pack.unverified_values():
        log.warning(
            "OPEN-2: %d rule value(s) not yet verified against the source circular: %s",
            len(unverified), ", ".join(unverified),
        )
    yield


app = FastAPI(
    title="Rakshak",
    version="0.1.0",
    lifespan=lifespan,
    description=(
        "Compliance-verification harness for autonomous payment-recovery agents. "
        "Verdicts are produced by a deterministic, versioned rule engine; the model "
        "layer only parses messy logs and writes explanations."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Correlation-Id", "X-Run-Id", "X-Rulepack-Version", "X-Idempotent-Replay"
    ],
)

for module in (routes_health, routes_rules, routes_verify, routes_reports, routes_runs):
    app.include_router(module.router, prefix=settings.API_PREFIX)
