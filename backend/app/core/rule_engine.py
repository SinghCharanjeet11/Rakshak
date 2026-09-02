"""The deterministic decision core — 02-system-design.md §A.4.

Pure functions. No I/O, no LLM, no network, no randomness, no clock reads. Identical
input always yields identical verdicts, which is what makes the idempotency claim in
§B.3 observable rather than merely asserted.

This is the only module in the system permitted to decide PASS/FAIL (invariant I1).

Conventions applied here, chosen once and documented so they are auditable:

* **IST is a fixed UTC+05:30 offset.** India observes no DST, so a fixed offset is exact
  and avoids depending on a tz database being present on the host.
* **Naive datetimes are read as UTC.** An agent log without an offset is ambiguous; UTC
  is the conservative reading and it is stated rather than left implicit.
* **A missing field is not automatically a violation.** `hours_between_at_least` fails on
  a missing endpoint (you cannot evidence a notice that is not there), but `max_value`
  and `flag_must_be_false` pass on absence — absence of evidence is not evidence of a
  breach, and a verifier that invents violations from sparse logs is worse than useless.
  Both behaviours are pinned by unit tests.
"""

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from pydantic import BaseModel, Field

from app.core.models import Action, ExemptionApplied, Violation
from app.core.rules_loader import (
    Condition,
    Exemption,
    FlagMustBeFalse,
    HoursBetweenAtLeast,
    IfAmountGtThenFlag,
    MaxValue,
    Rule,
    RulePack,
    TimestampHourBetween,
)

IST = timezone(timedelta(hours=5, minutes=30))

# (ok, offending_value) — offending_value is only meaningful when ok is False.
EvalResult = tuple[bool, str]


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _fmt(dt: datetime) -> str:
    return _as_utc(dt).isoformat()


# --------------------------------------------------------------------------
# One evaluator per condition kind (closed vocabulary — invariant I6)
# --------------------------------------------------------------------------


def eval_hours_between_at_least(a: Action, c: HoursBetweenAtLeast) -> EvalResult:
    earlier: Optional[datetime] = getattr(a, c.earlier, None)
    later: Optional[datetime] = getattr(a, c.later, None)

    if earlier is None:
        return False, f"{c.earlier} is missing (no evidence of notice)"
    if later is None:
        return False, f"{c.later} is missing (cannot verify the interval)"

    gap_hours = (_as_utc(later) - _as_utc(earlier)).total_seconds() / 3600.0
    if gap_hours >= c.hours:
        return True, ""
    if gap_hours < 0:
        return False, (
            f"{c.earlier} {_fmt(earlier)} is AFTER {c.later} {_fmt(later)} "
            f"({abs(gap_hours):.2f}h late; {c.hours:g}h required)"
        )
    return False, (
        f"{c.earlier} only {gap_hours:.2f}h before {c.later} ({c.hours:g}h required)"
    )


def eval_if_amount_gt_then_flag(a: Action, c: IfAmountGtThenFlag) -> EvalResult:
    amount = getattr(a, c.amount_field, None)
    if amount is None or amount <= c.threshold:
        return True, ""  # rule does not bite below the threshold
    if getattr(a, c.required_flag, None) is True:
        return True, ""
    flag = getattr(a, c.required_flag, None)
    shown = "missing" if flag is None else str(flag).lower()
    return False, (
        f"{c.amount_field} {amount:g} > {c.threshold:g} but {c.required_flag}={shown}"
    )


def eval_max_value(a: Action, c: MaxValue) -> EvalResult:
    value = getattr(a, c.field, None)
    if value is None:
        return True, ""  # absence of evidence is not evidence of a breach
    if value <= c.max:
        return True, ""
    return False, f"{c.field}={value:g} exceeds permitted maximum {c.max:g}"


def eval_flag_must_be_false(a: Action, c: FlagMustBeFalse) -> EvalResult:
    value = getattr(a, c.field, None)
    if not value:
        return True, ""
    return False, f"{c.field}=true"


def eval_timestamp_hour_between(a: Action, c: TimestampHourBetween) -> EvalResult:
    dt: Optional[datetime] = getattr(a, c.field, None)
    if dt is None:
        return True, ""
    local = _as_utc(dt).astimezone(IST)
    minutes = local.hour * 60 + local.minute
    if c.start_hour * 60 <= minutes <= c.end_hour * 60:
        return True, ""
    return False, (
        f"{c.field} {local.strftime('%H:%M')} IST is outside "
        f"{c.start_hour:02d}:00–{c.end_hour:02d}:00 IST"
    )


CONDITION_EVALUATORS: dict[str, Callable[[Action, Condition], EvalResult]] = {
    "hours_between_at_least": eval_hours_between_at_least,  # type: ignore[dict-item]
    "if_amount_gt_then_flag": eval_if_amount_gt_then_flag,  # type: ignore[dict-item]
    "max_value": eval_max_value,  # type: ignore[dict-item]
    "flag_must_be_false": eval_flag_must_be_false,  # type: ignore[dict-item]
    "timestamp_hour_between": eval_timestamp_hour_between,  # type: ignore[dict-item]
}


# --------------------------------------------------------------------------
# evaluate()
# --------------------------------------------------------------------------


class Evaluation(BaseModel):
    """Full result. `evaluate()` returns only the violations, per the design doc."""

    violations: list[Violation] = Field(default_factory=list)
    exemptions_applied: list[ExemptionApplied] = Field(default_factory=list)


def _violation(a: Action, rule: Rule, offending: str) -> Violation:
    return Violation(
        action_id=a.id,
        rule_id=rule.id,
        title=rule.title,
        severity=rule.severity,
        offending_value=offending,
        clause=rule.clause,
        source=rule.source,
    )


def _why_exempt(ex: Exemption, a: Action) -> str:
    """Name the selectors that actually matched.

    The report has to say *why* an action passed as exempt, and an exemption may match on
    MCC, on category, on an amount ceiling, or a combination. Reporting `mcc=None` for a
    category-based waiver would make a correct verdict look like a bug.
    """
    parts: list[str] = []
    if ex.when_mcc_in:
        parts.append(f"mcc={a.mcc}")
    if ex.when_category_in:
        parts.append(f"category={a.category.value if a.category else None}")
    if ex.max_amount is not None:
        parts.append(f"amount={a.amount} within {ex.max_amount:g}")
    return ", ".join(parts)


def evaluate_detailed(actions: list[Action], pack: RulePack) -> Evaluation:
    result = Evaluation()
    exemptions = pack.exemptions_for(actions)

    for a in actions:
        for rule in pack.rules_for(a.type):
            if (ex := exemptions.suppresses(rule.id, a)) is not None:
                result.exemptions_applied.append(
                    ExemptionApplied(
                        action_id=a.id,
                        rule_id=rule.id,
                        exemption_id=ex.id,
                        reason=f"{ex.title} ({_why_exempt(ex, a)})",
                        clause=ex.clause,
                        source=ex.source,
                    )
                )
                continue

            evaluator = CONDITION_EVALUATORS[rule.condition.kind]
            ok, offending = evaluator(a, rule.condition)
            if not ok:
                result.violations.append(_violation(a, rule, offending))

    return result


def evaluate(actions: list[Action], pack: RulePack) -> list[Violation]:
    """The contract quoted in 02-system-design.md §A.4 and used by the orchestrator."""
    return evaluate_detailed(actions, pack).violations
