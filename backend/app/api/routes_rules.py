"""Rule-pack inspection.

The rule-pack is a public artifact, not an implementation detail: `/rules` is what backs
the frontend viewer and what makes "these are inspectable, versioned, and cite the law"
a demonstrable claim rather than a slide.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.rules_loader import RulePackError, available_versions
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


@router.get("/rules/versions")
def get_versions() -> dict[str, object]:
    try:
        return {"versions": available_versions()}
    except RulePackError as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc
