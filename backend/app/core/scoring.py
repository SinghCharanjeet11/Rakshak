"""Aggregate compliance score — 02-system-design.md §A.5.

Deterministic, like everything else in `core/`. The report summary is generated here
too, and deliberately *not* by the LLM: the headline sentence a compliance officer reads
first must be derivable from the verdicts, not written by a model (invariant I1/I8).

    base      score = 100 * (passing_actions / total_actions)                # MVP
    weighted  score = 100 * (1 - Σweight(violations) / (total * max_weight))  # SHOULD

An action counts as *failed* if it carries at least one violation, so the base score is
per-action, not per-violation — three breaches on one debit is one failed action.
"""

from typing import Iterable

from pydantic import BaseModel

from app.core.models import Action, Severity, Violation

SEVERITY_WEIGHT: dict[Severity, float] = {
    Severity.CRITICAL: 3.0,
    Severity.HIGH: 2.0,
    Severity.MEDIUM: 1.5,
    Severity.LOW: 1.0,
}
MAX_WEIGHT = max(SEVERITY_WEIGHT.values())

_SEVERITY_ORDER = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]


class ScoreResult(BaseModel):
    score: float
    passed: int
    failed: int
    total: int
    mode: str


def severity_counts(violations: Iterable[Violation]) -> dict[Severity, int]:
    counts = {s: 0 for s in _SEVERITY_ORDER}
    for v in violations:
        counts[v.severity] += 1
    return counts


def compute(
    actions: list[Action],
    violations: list[Violation],
    mode: str = "base",
) -> ScoreResult:
    total = len(actions)
    failed_ids = {v.action_id for v in violations}
    # Count only failures that map to a submitted action, so a stray violation cannot
    # push `failed` above `total` and make the score negative.
    action_ids = {a.id for a in actions}
    failed = len(failed_ids & action_ids)
    passed = total - failed

    if total == 0:
        return ScoreResult(score=100.0, passed=0, failed=0, total=0, mode=mode)

    if mode == "weighted":
        penalty = sum(SEVERITY_WEIGHT[v.severity] for v in violations)
        raw = 100.0 * (1.0 - penalty / (total * MAX_WEIGHT))
        score = max(0.0, min(100.0, raw))
    else:
        score = 100.0 * passed / total

    return ScoreResult(score=round(score, 2), passed=passed, failed=failed, total=total, mode=mode)


def summarize(result: ScoreResult, violations: list[Violation]) -> str:
    """One deterministic headline sentence for the report."""
    if result.total == 0:
        return "No actions submitted."
    if not violations:
        return f"No violations across {result.total} actions. Fully compliant."

    counts = severity_counts(violations)
    breakdown = ", ".join(
        f"{n} {sev.value}" for sev in _SEVERITY_ORDER if (n := counts[sev])
    )
    worst = next((s for s in _SEVERITY_ORDER if counts[s]), None)
    worst_titles = sorted({v.title for v in violations if v.severity == worst})
    named = "; ".join(worst_titles[:2])
    if len(worst_titles) > 2:
        named += f"; +{len(worst_titles) - 2} more"

    return (
        f"{len(violations)} violation(s) across {result.total} actions "
        f"({result.failed} failed). {breakdown}. Most severe — {named}."
    )
