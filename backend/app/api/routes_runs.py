"""Run inspection, replay, and the audit trail.

Additive to the module list in 03-backend.md §2, which names four route modules but
specifies three `/runs/*` endpoints in its §1 API surface table. They live here rather
than being wedged into routes_verify.py, which is meant to stay a thin adapter.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api._auth import resolve_tenant
from app.core.models import Report
from app.core.rules_loader import RulePackError
from app.orchestration.eval_hooks import signals_for
from app.orchestration.orchestrator import replay as replay_run
from app.store import repository

router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}")
def get_run(run_id: str, tenant_id: str = Depends(resolve_tenant)) -> dict[str, object]:
    run = repository.get_run(run_id, tenant_id=tenant_id)
    if run is None:
        # 404 not 403 across a tenant boundary — see api/_auth.py.
        raise HTTPException(status_code=404, detail=f"no run {run_id}")

    report = repository.get_report_for_run(run_id, tenant_id=tenant_id)
    duration_ms = None
    if run.ended_at is not None:
        duration_ms = round((run.ended_at - run.started_at).total_seconds() * 1000, 2)

    return {
        "run": run.model_dump(mode="json"),
        "report_id": report.id if report else None,
        "duration_ms": duration_ms,
        "budget_remaining": {
            "turns": run.budget.max_total_turns - run.turns_used,
            "tokens": run.budget.max_tokens - run.tokens_used,
            "cost_inr": round(run.budget.max_cost_inr - run.cost_inr, 6),
        },
        "eval_signals": [s.model_dump(mode="json") for s in signals_for(run_id)],
    }


@router.get("/runs/{run_id}/audit")
def get_audit(run_id: str, tenant_id: str = Depends(resolve_tenant)) -> dict[str, object]:
    if repository.get_run(run_id, tenant_id=tenant_id) is None:
        raise HTTPException(status_code=404, detail=f"no run {run_id}")
    rows = repository.get_audit(run_id, tenant_id=tenant_id)
    return {
        "run_id": run_id,
        "append_only": True,
        "count": len(rows),
        "entries": rows,
    }


@router.post("/runs/{run_id}/replay", response_model=Report)
async def replay(
    run_id: str,
    response: Response,
    rulepack_version: Optional[str] = Query(default=None),
    tenant_id: str = Depends(resolve_tenant),
) -> Report:
    """Re-verify a stored run's raw log, optionally under a different rule-pack version."""
    if repository.get_run(run_id, tenant_id=tenant_id) is None:
        # Checked before replaying: replaying another tenant's log would both disclose it
        # and spend this tenant's budget doing so.
        raise HTTPException(status_code=404, detail=f"no run {run_id}")
    try:
        outcome = await replay_run(run_id, rulepack_version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RulePackError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response.headers["X-Correlation-Id"] = outcome.run.correlation_id
    response.headers["X-Run-Id"] = outcome.run.id
    response.headers["X-Idempotent-Replay"] = "true" if outcome.reused else "false"
    return outcome.report
