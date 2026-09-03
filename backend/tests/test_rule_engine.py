"""Per-condition unit tests + the golden batch test (02-system-design.md Part C).

The golden test is one of the three shown live in the demo: it proves the compliance
logic is correct, and it is the regression trap that fires if any rule silently changes.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.models import Severity, Violation
from app.core.rule_engine import (
    IST,
    eval_flag_must_be_false,
    eval_hours_between_at_least,
    eval_if_amount_gt_then_flag,
    eval_max_value,
    eval_timestamp_hour_between,
    evaluate,
    evaluate_detailed,
)
from app.core.rules_loader import (
    FlagMustBeFalse,
    HoursBetweenAtLeast,
    IfAmountGtThenFlag,
    MaxValue,
    TimestampHourBetween,
)
from app.core.scoring import compute, summarize
from tests.conftest import make_action

# --------------------------------------------------------------------------
# hours_between_at_least
# --------------------------------------------------------------------------

NOTICE_24H = HoursBetweenAtLeast(
    kind="hours_between_at_least", earlier="notice_sent_at", later="debit_due_at", hours=24
)


def test_hours_between_passes_at_exactly_the_boundary():
    due = datetime(2026, 8, 20, 12, 0, tzinfo=IST)
    a = make_action(notice_sent_at=due - timedelta(hours=24), debit_due_at=due)
    ok, _ = eval_hours_between_at_least(a, NOTICE_24H)
    assert ok, "24h notice is compliant; the comparison must be >=, not >"


def test_hours_between_fails_just_under_the_boundary():
    due = datetime(2026, 8, 20, 12, 0, tzinfo=IST)
    a = make_action(notice_sent_at=due - timedelta(hours=23, minutes=59), debit_due_at=due)
    ok, offending = eval_hours_between_at_least(a, NOTICE_24H)
    assert not ok
    assert "23.98h" in offending and "24h required" in offending


def test_hours_between_fails_when_notice_is_missing():
    a = make_action(debit_due_at=datetime(2026, 8, 20, 12, 0, tzinfo=IST))
    ok, offending = eval_hours_between_at_least(a, NOTICE_24H)
    assert not ok, "a notice that cannot be evidenced is not a notice"
    assert "missing" in offending


def test_hours_between_fails_when_notice_is_after_the_debit():
    due = datetime(2026, 8, 20, 12, 0, tzinfo=IST)
    a = make_action(notice_sent_at=due + timedelta(hours=3), debit_due_at=due)
    ok, offending = eval_hours_between_at_least(a, NOTICE_24H)
    assert not ok
    assert "AFTER" in offending


def test_hours_between_treats_naive_datetimes_as_utc():
    a = make_action(
        notice_sent_at=datetime(2026, 8, 19, 12, 0),
        debit_due_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
    )
    ok, _ = eval_hours_between_at_least(a, NOTICE_24H)
    assert ok


# --------------------------------------------------------------------------
# if_amount_gt_then_flag
# --------------------------------------------------------------------------

AFA = IfAmountGtThenFlag(
    kind="if_amount_gt_then_flag",
    amount_field="amount",
    threshold=15000,
    required_flag="afa_present",
)


@pytest.mark.parametrize(
    "amount,afa,expected",
    [
        (14999.0, False, True),   # under threshold, no AFA needed
        (15000.0, False, True),   # AT the threshold — "above" means strictly greater
        (15000.01, False, False),
        (20000.0, False, False),
        (20000.0, True, True),    # over threshold but authenticated
        (20000.0, None, False),   # flag absent is not the same as flag true
        (None, False, True),      # no amount, rule cannot bite
    ],
)
def test_afa_threshold(amount, afa, expected):
    a = make_action(amount=amount, afa_present=afa)
    ok, _ = eval_if_amount_gt_then_flag(a, AFA)
    assert ok is expected


def test_afa_offending_value_names_both_the_amount_and_the_flag():
    a = make_action(amount=20000.0, afa_present=False)
    _, offending = eval_if_amount_gt_then_flag(a, AFA)
    assert "20000" in offending and "15000" in offending and "afa_present=false" in offending


# --------------------------------------------------------------------------
# max_value
# --------------------------------------------------------------------------

RETRY_CAP = MaxValue(kind="max_value", field="retry_index", max=4)


# NPCI permits four attempts per mandate — one original plus three retries — so attempt 4
# is the last permitted one and attempt 5 is the first breach. `retry_index` counts
# attempts, not retries; getting that boundary wrong in either direction is a false
# verdict on a real payment, so both sides of it are pinned here.
@pytest.mark.parametrize(
    "retry_index,expected",
    [(1, True), (3, True), (4, True), (5, False), (None, True)],
)
def test_retry_cap(retry_index, expected):
    a = make_action(type="mandate_retry", retry_index=retry_index)
    ok, _ = eval_max_value(a, RETRY_CAP)
    assert ok is expected


# --------------------------------------------------------------------------
# flag_must_be_false
# --------------------------------------------------------------------------

DISPUTE = FlagMustBeFalse(kind="flag_must_be_false", field="dispute_active")


@pytest.mark.parametrize("flag,expected", [(False, True), (None, True), (True, False)])
def test_flag_must_be_false(flag, expected):
    a = make_action(dispute_active=flag)
    ok, _ = eval_flag_must_be_false(a, DISPUTE)
    assert ok is expected


# --------------------------------------------------------------------------
# timestamp_hour_between
# --------------------------------------------------------------------------

QUIET = TimestampHourBetween(
    kind="timestamp_hour_between", field="timestamp", start_hour=9, end_hour=21
)


@pytest.mark.parametrize(
    "hour,minute,expected",
    [
        (9, 0, True),    # opening edge
        (12, 0, True),
        (20, 59, True),
        (21, 0, True),   # closing edge is inclusive
        (21, 1, False),
        (23, 30, False),
        (8, 59, False),
        (3, 0, False),
    ],
)
def test_quiet_hours_in_ist(hour, minute, expected):
    a = make_action(type="contact", timestamp=datetime(2026, 8, 20, hour, minute, tzinfo=IST))
    ok, _ = eval_timestamp_hour_between(a, QUIET)
    assert ok is expected


def test_quiet_hours_converts_utc_to_ist_before_judging():
    # 18:00 UTC == 23:30 IST — compliant in UTC, a violation in IST.
    a = make_action(type="contact", timestamp=datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc))
    ok, offending = eval_timestamp_hour_between(a, QUIET)
    assert not ok
    assert "23:30 IST" in offending


# --------------------------------------------------------------------------
# GOLDEN BATCH TEST — the regression trap
# --------------------------------------------------------------------------

EXPECTED_VIOLATIONS = {
    ("a_v01", "RETRY_CAP_PER_WINDOW"),
    ("a_v02", "PRE_DEBIT_NOTICE_24H"),
    ("a_v03", "AFA_ABOVE_THRESHOLD"),
    ("a_v04", "NO_RETRY_UNDER_DISPUTE"),
    ("a_v05", "QUIET_HOURS"),
    ("a_v06", "RESPECT_OPT_OUT"),
}


def test_golden_clean_batch_has_zero_violations(clean_actions, pack):
    violations = evaluate(clean_actions, pack)
    assert violations == [], f"false positives on the clean batch: {violations}"


def test_golden_violating_batch_matches_exactly(violating_actions, pack):
    violations = evaluate(violating_actions, pack)
    assert {(v.action_id, v.rule_id) for v in violations} == EXPECTED_VIOLATIONS


def test_golden_every_violation_is_fully_cited(violating_actions, pack):
    """Invariant I5: a FAIL always names rule, clause, source and offending value."""
    for v in evaluate(violating_actions, pack):
        assert v.rule_id and v.title and v.clause and v.source and v.offending_value
        assert v.explanation is None, "the engine must never write prose"


def test_fastag_exemption_makes_a_short_notice_debit_pass(violating_actions, pack):
    """The demo money-shot. If this flips to FAIL, the tool is trigger-happy."""
    result = evaluate_detailed(violating_actions, pack)

    assert not any(v.action_id == "a_v07" for v in result.violations)
    applied = [e for e in result.exemptions_applied if e.action_id == "a_v07"]
    assert len(applied) == 1
    assert applied[0].rule_id == "PRE_DEBIT_NOTICE_24H"
    assert applied[0].exemption_id == "EXEMPT_MCC_SKIP_NOTICE"


def test_exemption_does_not_leak_to_other_rules(pack):
    """A FASTag MCC must not excuse a missing AFA — it exempts notice only."""
    a = make_action(
        id="a_leak", type="debit", amount=20000.0, afa_present=False, mcc="4784",
        notice_sent_at=datetime(2026, 8, 20, 15, 0, tzinfo=IST),
        debit_due_at=datetime(2026, 8, 20, 17, 0, tzinfo=IST),
    )
    rule_ids = {v.rule_id for v in evaluate([a], pack)}
    assert rule_ids == {"AFA_ABOVE_THRESHOLD"}


def test_exemption_does_not_apply_to_a_non_exempt_mcc(pack):
    a = make_action(
        id="a_mcc", type="debit", amount=250.0, mcc="5411",
        notice_sent_at=datetime(2026, 8, 20, 15, 0, tzinfo=IST),
        debit_due_at=datetime(2026, 8, 20, 17, 0, tzinfo=IST),
    )
    assert {v.rule_id for v in evaluate([a], pack)} == {"PRE_DEBIT_NOTICE_24H"}


def test_evaluate_is_deterministic(violating_actions, pack):
    """Same input, same verdicts — the basis of the idempotency claim (§B.3)."""
    first = evaluate(violating_actions, pack)
    second = evaluate(violating_actions, pack)
    assert [v.model_dump() for v in first] == [v.model_dump() for v in second]


def test_escalate_has_no_applicable_rules(pack):
    assert evaluate([make_action(id="a_esc", type="escalate")], pack) == []


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------


def test_score_of_clean_batch_is_100(clean_actions, pack):
    result = compute(clean_actions, evaluate(clean_actions, pack))
    assert result.score == 100.0
    assert result.failed == 0 and result.passed == 13


def test_score_of_combined_batch(clean_actions, violating_actions, pack):
    actions = clean_actions + violating_actions
    violations = evaluate(actions, pack)
    result = compute(actions, violations)

    assert result.total == 23
    assert result.failed == 6
    assert result.passed == 17
    assert result.score == 73.91


def test_weighted_score_penalises_critical_violations_harder(
    clean_actions, violating_actions, pack
):
    actions = clean_actions + violating_actions
    violations = evaluate(actions, pack)
    base = compute(actions, violations, mode="base").score
    weighted = compute(actions, violations, mode="weighted").score
    assert weighted != base
    assert 0.0 <= weighted <= 100.0


def test_score_never_goes_negative():
    """Many criticals on one action would drive the weighted formula below zero."""
    a = make_action(id="a_x")
    many = [
        Violation(
            action_id="a_x", rule_id=f"R{i}", title="t", severity=Severity.CRITICAL,
            offending_value="o", clause="c", source="s",
        )
        for i in range(50)
    ]
    assert compute([a], many, mode="weighted").score == 0.0


def test_stray_violation_cannot_push_failed_above_total():
    a = make_action(id="a_present")
    stray = Violation(
        action_id="a_absent", rule_id="R", title="t", severity=Severity.HIGH,
        offending_value="o", clause="c", source="s",
    )
    result = compute([a], [stray])
    assert result.failed == 0 and result.passed == 1 and result.score == 100.0


def test_summary_names_the_most_severe_rule(violating_actions, pack):
    violations = evaluate(violating_actions, pack)
    result = compute(violating_actions, violations)
    summary = summarize(result, violations)
    assert "6 violation(s) across 10 actions" in summary
    assert "critical" in summary


def test_summary_of_a_clean_batch_says_so(clean_actions, pack):
    result = compute(clean_actions, [])
    assert "Fully compliant" in summarize(result, [])


# --------------------------------------------------------------------------
# NO_DEBIT_AFTER_OPT_OUT — §6(c), added 2026-09-02
# --------------------------------------------------------------------------


def _lawful_debit(**over):
    """A debit that breaks nothing, so a test can isolate the one rule it is about.

    Notice fields are required: a debit with no evidence of a pre-debit notice correctly
    fails PRE_DEBIT_NOTICE_24H, which would otherwise mask what these tests assert.
    """
    base = dict(
        type="debit",
        amount=500.0,
        notice_sent_at=datetime(2026, 8, 19, 10, 0, tzinfo=IST),
        debit_due_at=datetime(2026, 8, 20, 12, 0, tzinfo=IST),
    )
    base.update(over)
    return make_action(**base)


def test_debit_after_mandate_opt_out_fails(pack):
    """The opt-out the circular actually grants is from a debit, not from contact."""
    a = _lawful_debit(mandate_opted_out=True)
    v = evaluate([a], pack)
    assert [x.rule_id for x in v] == ["NO_DEBIT_AFTER_OPT_OUT"]
    assert v[0].clause == "RBI/DPSS/2026-27/396 §6(c)"
    assert v[0].severity.value == "critical"


def test_contact_opt_out_does_not_block_a_lawful_debit(pack):
    """The false positive this rule was deliberately kept separate to avoid.

    A customer who unsubscribed from marketing SMS has `consent_opted_out=true` and has NOT
    opted out of the mandate. Debiting them is lawful, and sharing one field between the
    two rules would have failed it.
    """
    a = _lawful_debit(consent_opted_out=True)
    assert [x.rule_id for x in evaluate([a], pack)] == []


def test_mandate_opt_out_does_not_fire_on_a_contact(pack):
    """RESPECT_OPT_OUT covers outreach; this rule must not double up on it."""
    a = make_action(type="contact", channel="sms", mandate_opted_out=True)
    assert "NO_DEBIT_AFTER_OPT_OUT" not in {x.rule_id for x in evaluate([a], pack)}


def test_absent_opt_out_flag_passes(pack):
    """A sparse log is the norm; a missing flag is not an opt-out."""
    a = _lawful_debit()
    assert "NO_DEBIT_AFTER_OPT_OUT" not in {x.rule_id for x in evaluate([a], pack)}
