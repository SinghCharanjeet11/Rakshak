"""The real Razorpay capture, end to end.

`razorpay_webhooks.json` is synthetic — written to representative shapes. This file tests
against `razorpay_webhooks_real.json`, which holds **real payment entities pulled from a
live Razorpay test-mode account** (see `scripts/fetch_razorpay.py`). It closes the
`00-overview.md` MUST: "one real Razorpay test-mode webhook sequence run through it".

The assertions are deliberately written as **invariants rather than a fixed expected set**,
because the fixture is regenerable — re-running the fetch script with more payments must not
break the suite. What is pinned is the behaviour that must hold for any capture:

  * every mappable event becomes exactly one Action, and unmappable ones are ignored
  * a debit above the AFA threshold without AFA always fails, whatever its id
  * a debit with no notice evidence always fails — absence of evidence is not a pass
  * no field the adapter invents survives the membrane

The suite skips itself if the capture is absent, so a fresh clone without Razorpay
credentials still runs green.
"""

import json

import pytest

from app.adapters.razorpay import EVENT_MAP, map_webhook_payload
from app.core.models import Action
from app.core.rule_engine import evaluate_detailed
from tests.conftest import SEED_DIR

REAL = SEED_DIR / "razorpay_webhooks_real.json"

pytestmark = pytest.mark.skipif(
    not REAL.exists(),
    reason="no real Razorpay capture — run scripts/fetch_razorpay.py with test-mode keys",
)


@pytest.fixture(scope="module")
def capture() -> dict:
    return json.loads(REAL.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def actions(capture) -> list[Action]:
    return [Action.model_validate(a) for a in map_webhook_payload(capture)]


def test_the_capture_is_labelled_as_reconstructed(capture):
    """The envelope around each payment is rebuilt by the fetch script, not captured —
    Razorpay blocklists request-bin hostnames. The file must say so, so nobody later
    describes it in a pitch as a captured webhook delivery."""
    source = capture.get("_source", "")
    assert "Razorpay test-mode API" in source
    assert "reconstructed" in source


def test_every_mappable_event_becomes_exactly_one_action(capture, actions):
    mappable = [e for e in capture["events"] if e.get("event") in EVENT_MAP]
    assert len(actions) == len(mappable)
    assert len({a.id for a in actions}) == len(actions), "action ids must be unique"


def test_amounts_are_rupees_not_paise(actions):
    """Razorpay reports the smallest currency unit. A missed /100 would move actions
    across the AFA threshold by two orders of magnitude."""
    for a in actions:
        if a.amount is not None:
            assert a.amount < 1_000_000, f"{a.id} amount {a.amount} looks like paise"


def test_no_action_carries_a_field_outside_the_schema(capture):
    """`Action` is extra="forbid", so this would already raise — the assertion documents
    that the adapter's output crosses the same membrane as any model output."""
    for raw in map_webhook_payload(capture):
        Action.model_validate(raw)


# --------------------------------------------------------------------------
# the rules, against real money
# --------------------------------------------------------------------------


def test_a_real_debit_over_the_threshold_without_afa_fails(actions, pack):
    """The demo's central claim: Razorpay captured this payment happily; Rakshak says it
    breached. Payment success and compliance are different questions."""
    over = [
        a for a in actions
        if a.type.value == "debit" and (a.amount or 0) > 15000 and a.afa_present is not True
    ]
    if not over:
        pytest.skip("this capture has no debit above the AFA threshold")

    violations = evaluate_detailed(actions, pack).violations
    for a in over:
        rules = {v.rule_id for v in violations if v.action_id == a.id}
        assert "AFA_ABOVE_THRESHOLD" in rules, f"{a.id} (Rs {a.amount:,.0f}) should fail AFA"


def test_a_real_debit_with_no_notice_evidence_fails(actions, pack):
    """Razorpay webhooks carry no compliance evidence, so a merchant who stamps no
    rakshak_notice_sent_at note produces a debit that cannot be shown to be lawful.
    That must FAIL — a verifier that passes unevidenced debits verifies nothing."""
    bare = [a for a in actions if a.type.value == "debit" and a.notice_sent_at is None]
    if not bare:
        pytest.skip("every debit in this capture carries notice evidence")

    violations = evaluate_detailed(actions, pack).violations
    for a in bare:
        rules = {v.rule_id for v in violations if v.action_id == a.id}
        assert "PRE_DEBIT_NOTICE_24H" in rules
        offending = next(
            v.offending_value for v in violations
            if v.action_id == a.id and v.rule_id == "PRE_DEBIT_NOTICE_24H"
        )
        assert "missing" in offending, "the report must say the notice is absent, not late"


def test_a_debit_with_48h_notice_under_the_threshold_passes(actions, pack):
    """The other half: real, evidenced, compliant payments must come back clean, or the
    tool is trigger-happy and its failures mean nothing."""
    ok = [
        a for a in actions
        if a.type.value == "debit"
        and a.notice_sent_at is not None
        and (a.amount or 0) <= 15000
    ]
    if not ok:
        pytest.skip("this capture has no compliant debit")

    violations = evaluate_detailed(actions, pack).violations
    for a in ok:
        assert not [v for v in violations if v.action_id == a.id], (
            f"{a.id} is evidenced and under threshold — it must pass"
        )


def test_every_violation_cites_a_clause(actions, pack):
    for v in evaluate_detailed(actions, pack).violations:
        assert v.clause and v.source and v.offending_value


def test_failed_payments_become_retries_not_debits(capture, actions):
    """A failed Razorpay payment is an attempt, not a completed debit — mapping it to
    `debit` would invent a money movement that never happened."""
    failed_ids = {
        e["payload"]["payment"]["entity"]["id"]
        for e in capture["events"]
        if e.get("event") == "payment.failed"
    }
    for a in actions:
        if a.id in failed_ids:
            assert a.type.value == "mandate_retry"
