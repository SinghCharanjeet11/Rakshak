"""Rule-pack inspection.

The rule-pack is a public artifact, not an implementation detail: `/rules` is what backs
the frontend viewer and what makes "these are inspectable, versioned, and cite the law"
a demonstrable claim rather than a slide.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.rules_loader import RulePackError, available_versions
from app.llm._provider import LLMUnavailable
from app.llm.rule_drafting_agent import draft_rule
from app.orchestration.orchestrator import get_pack

router = APIRouter(tags=["rules"])

# Human-readable renderings of the closed condition vocabulary, for the UI.
CONDITION_PROSE = {
    "hours_between_at_least": "{later} must be at least {hours}h after {earlier}",
    "if_amount_gt_then_flag": "if {amount_field} > {threshold:g} then {required_flag} must be true",
    "max_value": "{field} must not exceed {max:g}",
    "flag_must_be_false": "{field} must be false",
    "timestamp_hour_between": "{field} must fall between {start_hour:02d}:00 and {end_hour:02d}:00 IST",
}


def _describe(condition) -> str:
    template = CONDITION_PROSE.get(condition.kind)
    if not template:  # pragma: no cover - closed vocabulary
        return condition.kind
    return template.format(**condition.model_dump())


@router.get("/rules")
def get_rules(version: Optional[str] = Query(default=None)) -> dict[str, object]:
    try:
        pack = get_pack(version)
    except RulePackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "version": pack.version,
        "source": pack.source,
        "circular": pack.circular,
        "sources": [s.model_dump(mode="json") for s in pack.sources],
        "unverified_rule_values": pack.unverified_values(),
        "rules": [
            {
                "id": r.id,
                "title": r.title,
                "applies_to": [t.value for t in r.applies_to],
                "severity": r.severity.value,
                "clause": r.clause,
                "source": r.source,
                "condition": r.condition.model_dump(),
                "condition_prose": _describe(r.condition),
                "value_verified": r.value_verified,
                "verified_on": r.verified_on,
                # Display-only evidence: the reader compares `clause_text` against
                # `condition` and decides for themselves whether we read the law right.
                "clause_text": r.clause_text,
            }
            for r in pack.rules
        ],
        "exemptions": [
            {
                "id": e.id,
                "title": e.title,
                "exempts": e.exempts,
                "when_mcc_in": e.when_mcc_in,
                "when_category_in": [c.value for c in e.when_category_in],
                "max_amount": e.max_amount,
                "clause": e.clause,
                "source": e.source,
                "value_verified": e.value_verified,
                "verified_on": e.verified_on,
                "clause_text": e.clause_text,
            }
            for e in pack.exemptions
        ],
    }


class DraftRuleBody(BaseModel):
    """Clause text a human pasted, plus an optional steer for the drafter."""

    clause_text: str = Field(min_length=20, max_length=20_000)
    hint: Optional[str] = Field(default=None, max_length=500)


@router.post("/rules/draft")
async def draft_rule_endpoint(body: DraftRuleBody) -> dict[str, object]:
    """Propose a rule-pack entry from regulation text. **Writes nothing.**

    Read that literally: this handler has no access to the rules directory and calls
    nothing that does. The response is a proposal a human reads, edits and commits by
    hand, which is what keeps the shipped artifact deterministic data rather than model
    output. `tests/test_rule_drafting.py` asserts the active pack is byte-identical
    before and after a call.
    """
    try:
        result = await draft_rule(body.clause_text, body.hint)
    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"the drafting layer is unreachable ({exc}). Rule authoring needs a model; "
                "verification does not, and is unaffected."
            ),
        ) from exc

    return {
        "drafted": result.drafted,
        # accepted means it survived the closed-vocabulary membrane, NOT that it is right.
        "accepted": result.accepted,
        "kind": result.kind,
        "reason": result.reason,
        "rejection": result.rejection,
        "yaml": result.yaml,
        "rule": result.rule.model_dump(mode="json") if result.rule else None,
        "exemption": result.exemption.model_dump(mode="json") if result.exemption else None,
        "tokens_used": result.usage.total_tokens,
        "cost_inr": result.usage.cost_inr,
        "review_required": True,
    }


@router.get("/rules/versions")
def get_versions() -> dict[str, object]:
    try:
        return {"versions": available_versions()}
    except RulePackError as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc
