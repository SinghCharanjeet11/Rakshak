"""Verification endpoints — a thin HTTP adapter.

Contains no pipeline logic. It validates the envelope, resolves the tenant, derives the
idempotency key, hands off to the orchestrator, and maps failures onto status codes
(03-backend.md §1). Everything interesting happens behind `run_verification`.
"""

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.api._auth import resolve_tenant
from app.core.models import Report
from app.core.rules_loader import RulePackError
from app.llm._provider import LLMUnavailable
from app.orchestration.membrane import MembraneError
from app.orchestration.orchestrator import VerifyRequest, run_verification

router = APIRouter(tags=["verify"])


class VerifyBatchBody(BaseModel):
    format: Literal["json", "text", "razorpay"] = "json"
    payload: Any
    rulepack_version: Optional[str] = None
    idempotency_key: Optional[str] = None


class VerifyOneBody(BaseModel):
    action: dict[str, Any]
    rulepack_version: Optional[str] = None


async def _dispatch(
    body: VerifyBatchBody, tenant_id: str, response: Response
) -> Report:
    try:
        outcome = await run_verification(
            VerifyRequest(
                format=body.format,
                payload=body.payload,
                rulepack_version=body.rulepack_version,
                idempotency_key=body.idempotency_key,
                tenant_id=tenant_id,
            )
        )
    except (RulePackError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MembraneError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"the parsing layer is unreachable ({exc}). "
                'Submit format:"json" with structured actions to bypass parsing — '
                "verdicts never depend on the model."
            ),
        ) from exc

    response.headers["X-Correlation-Id"] = outcome.run.correlation_id
    response.headers["X-Run-Id"] = outcome.run.id
    response.headers["X-Rulepack-Version"] = outcome.run.rulepack_version
    response.headers["X-Idempotent-Replay"] = "true" if outcome.reused else "false"
    return outcome.report


@router.post("/verify/batch", response_model=Report)
async def verify_batch(
    body: VerifyBatchBody,
    response: Response,
    tenant_id: str = Depends(resolve_tenant),
) -> Report:
    return await _dispatch(body, tenant_id, response)


@router.post("/verify", response_model=Report)
async def verify_one(
    body: VerifyOneBody,
    response: Response,
    tenant_id: str = Depends(resolve_tenant),
) -> Report:
    """Single action — the batch path with a one-item payload. Same membrane, same core."""
    batch = VerifyBatchBody(
        format="json", payload=[body.action], rulepack_version=body.rulepack_version
    )
    return await _dispatch(batch, tenant_id, response)
