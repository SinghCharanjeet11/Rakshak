"""The rule-drafting agent and its membrane.

The claim under test is narrow and load-bearing: a model may *propose* law, and cannot
*enact* it. Every test here is either "a bad proposal is rejected" or "nothing was
written". No test reaches a provider -- conftest blanks the key, and `validate_draft` is
pure so a compromised model's output can be handed to it directly.
"""

import hashlib
from pathlib import Path

import pytest

from app.core.rules_loader import DEFAULT_RULES_DIR, load_pack
from app.llm.rule_drafting_agent import DRAFTING_TOOLS, validate_draft

VALID_RULE = {
    "drafted": True,
    "kind": "rule",
    "rule": {
        "id": "POST_DEBIT_NOTICE",
        "title": "Post-transaction notification must be sent",
        "applies_to": ["debit"],
        "severity": "medium",
        "clause": "RBI/DPSS/2026-27/396 §7",
        "clause_text": "An issuer shall send a post-transaction notification to the customer.",
        "condition": {"kind": "flag_must_be_false", "field": "dispute_active"},
    },
}


def _pack_fingerprint() -> str:
    """Hash of every rule-pack file on disk, to prove nothing was written."""
    h = hashlib.sha256()
    for p in sorted(Path(DEFAULT_RULES_DIR).glob("*.yaml")):
        h.update(p.read_bytes())
    return h.hexdigest()


# --------------------------------------------------------------------------
# least privilege
# --------------------------------------------------------------------------


def test_the_drafter_declares_no_tools():
    """Like the explainer. It reads a passage a human pasted; it needs nothing else."""
    assert DRAFTING_TOOLS == []


# --------------------------------------------------------------------------
# the membrane — a model may propose, not enact
# --------------------------------------------------------------------------


def test_a_valid_draft_is_accepted_and_rendered_as_yaml():
    r = validate_draft(VALID_RULE)
    assert r.accepted and r.kind == "rule"
    assert r.rule.id == "POST_DEBIT_NOTICE"
    assert "clause_text: >-" in r.yaml
    assert "POST_DEBIT_NOTICE" in r.yaml


def test_an_invented_condition_kind_is_rejected():
    """Invariant I6 applied to authoring.

    This is the whole architectural point: the closed vocabulary that stops a hallucinated
    rule is the same mechanism that stops a hallucinated action. A model that invents a
    condition kind is refused here exactly as it would be refused at load.
    """
    bad = {**VALID_RULE, "rule": {**VALID_RULE["rule"],
                                  "condition": {"kind": "vibes_based_check", "field": "amount"}}}
    r = validate_draft(bad)
    assert not r.accepted
    assert "vibes_based_check" in r.rejection
    assert "closed vocabulary" in r.rejection


def test_a_condition_missing_required_fields_is_rejected():
    bad = {**VALID_RULE, "rule": {**VALID_RULE["rule"],
                                  "condition": {"kind": "max_value", "field": "retry_index"}}}
    assert not validate_draft(bad).accepted


def test_an_unknown_severity_is_rejected():
    bad = {**VALID_RULE, "rule": {**VALID_RULE["rule"], "severity": "catastrophic"}}
    assert not validate_draft(bad).accepted


def test_an_unknown_action_type_is_rejected():
    bad = {**VALID_RULE, "rule": {**VALID_RULE["rule"], "applies_to": ["teleport"]}}
    assert not validate_draft(bad).accepted


def test_a_model_cannot_mark_its_own_draft_verified():
    """The one field where a confident model could do real damage.

    `value_verified: true` is a claim that a human read the circular. A model asserting it
    would launder its own guess into the exact signal the dashboard uses to tell a
    reviewer what still needs checking.
    """
    sneaky = {**VALID_RULE, "rule": {**VALID_RULE["rule"],
                                     "value_verified": True, "verified_on": "2026-09-03"}}
    r = validate_draft(sneaky)
    assert r.accepted
    assert r.rule.value_verified is False
    assert r.rule.verified_on is None
    assert "value_verified" not in r.yaml.split("#")[0]


def test_the_membrane_checks_shape_not_meaning():
    """The limitation that makes human review mandatory rather than advisory.

    Observed on a live run of §6(a): the drafter produced `earlier: timestamp` where the
    law means `notice_sent_at`. Both are real Action fields, so the draft is structurally
    perfect and semantically wrong -- it would check whether the action occurred 24h before
    the debit, not whether the notice did.

    Nothing mechanical can catch that. It is caught by a person reading `clause_text`
    beside `condition`, which is why the two are rendered together and why `accepted`
    deliberately does not mean "correct". This test exists so nobody later mistakes the
    membrane for a correctness check.
    """
    plausible_but_wrong = {
        "drafted": True,
        "kind": "rule",
        "rule": {
            "id": "PRE_TRANSACTION_NOTIFICATION_24H",
            "title": "Pre-transaction notification must precede the debit by 24 hours",
            "applies_to": ["debit"],
            "severity": "high",
            "clause": "RBI/DPSS/2026-27/396 §6(a)",
            "clause_text": "An issuer shall send a pre-transaction notification to the "
                           "customer, at least 24 hours prior to the actual charge / debit.",
            # Wrong field: the law is about when the NOTICE was sent, not when the action ran.
            "condition": {
                "kind": "hours_between_at_least",
                "earlier": "timestamp",
                "later": "debit_due_at",
                "hours": 24,
            },
        },
    }
    r = validate_draft(plausible_but_wrong)
    assert r.accepted, "a wrong-but-well-formed draft passes validation, by design"
    assert r.rule.condition.earlier == "timestamp"
    # The evidence a reviewer needs to spot it is carried alongside, not discarded.
    assert "notification" in r.rule.clause_text
    assert "clause_text" in r.yaml and "condition" in r.yaml


def test_an_exemption_with_no_selector_is_rejected():
    """An exemption matching everything is a blanket false PASS."""
    r = validate_draft({
        "drafted": True,
        "kind": "exemption",
        "exemption": {
            "id": "EXEMPT_EVERYTHING",
            "title": "Exempt",
            "exempts": ["AFA_ABOVE_THRESHOLD"],
            "clause": "made up",
        },
    })
    assert not r.accepted
    assert "selector" in r.rejection


def test_a_declined_draft_is_reported_not_faked():
    """An honest refusal beats an invented rule, and must survive as a refusal."""
    r = validate_draft({"drafted": False, "reason": "the passage sets no testable condition"})
    assert not r.drafted and not r.accepted
    assert "no testable condition" in r.reason


def test_garbage_from_the_model_is_rejected_without_raising():
    for junk in [None, [], "a string", {}, {"drafted": True, "kind": "rule"}]:
        r = validate_draft(junk)
        assert not r.accepted


# --------------------------------------------------------------------------
# it writes nothing
# --------------------------------------------------------------------------


def test_validating_a_draft_does_not_touch_the_rule_pack():
    before = _pack_fingerprint()
    for payload in [VALID_RULE, {"drafted": False, "reason": "x"}]:
        validate_draft(payload)
    assert _pack_fingerprint() == before, "drafting must never write to the rule-pack"


def test_the_active_pack_is_unchanged_by_a_draft():
    """A proposal is not a rule until a human commits it."""
    before = {r.id for r in load_pack().rules}
    validate_draft(VALID_RULE)
    assert {r.id for r in load_pack().rules} == before
    assert "POST_DEBIT_NOTICE" not in before


# --------------------------------------------------------------------------
# the endpoint
# --------------------------------------------------------------------------


def test_draft_endpoint_is_502_without_a_model_and_says_verification_is_unaffected(client):
    """Authoring needs a model; verification never does. The error must say so, because
    the opposite impression would undermine the product's central claim."""
    r = client.post(
        "/api/v1/rules/draft",
        json={"clause_text": "An issuer shall send a pre-transaction notification at least 24 hours prior."},
    )
    assert r.status_code == 502
    assert "verification does not" in r.json()["detail"]


def test_draft_endpoint_rejects_a_too_short_passage(client):
    r = client.post("/api/v1/rules/draft", json={"clause_text": "too short"})
    assert r.status_code == 422


def test_draft_endpoint_does_not_mutate_the_pack(client):
    before = _pack_fingerprint()
    client.post(
        "/api/v1/rules/draft",
        json={"clause_text": "An issuer shall send a pre-transaction notification, at least 24 hours prior to the debit."},
    )
    assert _pack_fingerprint() == before


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
