"""The validation membrane — 02-system-design.md Part C.

The third of the three tests shown live. Together with the golden and isolation tests it
proves the compliance logic is correct, AI-independent, and structurally protected from
model error.
"""

import pytest

from app.core.rule_engine import evaluate
from app.orchestration.eval_hooks import SINK, scan_for_injection, signals_for
from app.orchestration.membrane import (
    MembraneError,
    validate_membrane,
    validate_membrane_detailed,
)
from tests.conftest import seed_text

GOOD = {
    "id": "a_1",
    "type": "debit",
    "timestamp": "2026-08-20T14:00:00+05:30",
    "amount": 4999.0,
}


def test_valid_items_pass():
    result = validate_membrane_detailed([GOOD], "run_t1")
    assert len(result.actions) == 1
    assert result.rejections == []
    assert result.rejection_rate == 0.0


def test_hallucinated_field_is_rejected_not_ignored():
    """Invariant I3. With Pydantic's default extra="ignore" this item would sail through
    as valid, which is exactly the failure the membrane exists to prevent."""
    fabricated = {**GOOD, "verdict": "compliant", "compliance_score": 100}
    result = validate_membrane_detailed([fabricated], "run_t2")

    assert result.actions == []
    assert len(result.rejections) == 1
    assert "extra" in result.rejections[0].reason.lower() or "verdict" in result.rejections[0].reason


def test_invented_enum_value_is_rejected():
    result = validate_membrane_detailed([{**GOOD, "type": "auto_approve"}], "run_t3")
    assert result.actions == []
    assert len(result.rejections) == 1


def test_malformed_timestamp_is_rejected():
    result = validate_membrane_detailed([{**GOOD, "timestamp": "last tuesday"}], "run_t4")
    assert result.actions == []
    assert "timestamp" in result.rejections[0].reason


def test_missing_required_field_is_rejected():
    result = validate_membrane_detailed([{"type": "debit", "timestamp": GOOD["timestamp"]}], "run_t5")
    assert result.actions == []
    assert "id" in result.rejections[0].reason


def test_valid_items_survive_alongside_rejected_ones():
    """A partial parse must not discard the good rows — and must not keep the bad ones."""
    result = validate_membrane_detailed(
        [GOOD, {**GOOD, "id": "a_2", "amount": "not a number"}, {**GOOD, "id": "a_3"}],
        "run_t6",
    )
    assert [a.id for a in result.actions] == ["a_1", "a_3"]
    assert result.rejection_rate == pytest.approx(1 / 3)


def test_accepts_the_actions_envelope():
    assert len(validate_membrane({"actions": [GOOD]}, "run_t7")) == 1


def test_accepts_a_json_string_with_code_fences():
    raw = '```json\n{"actions": [' + str(GOOD).replace("'", '"') + "]}\n```"
    assert len(validate_membrane(raw, "run_t8")) == 1


def test_non_list_payload_raises():
    with pytest.raises(MembraneError):
        validate_membrane({"result": "everything is fine"}, "run_t9")


def test_unparseable_string_raises():
    with pytest.raises(MembraneError, match="not valid JSON"):
        validate_membrane("the agent behaved itself", "run_t10")


def test_payload_above_the_action_cap_raises():
    with pytest.raises(MembraneError, match="above the run budget cap"):
        validate_membrane_detailed([GOOD] * 5, "run_t11", max_actions=4)


def test_membrane_emits_the_rejection_signal():
    SINK.clear()
    validate_membrane_detailed([GOOD, {**GOOD, "id": "a_2", "type": "nope"}], "run_sig")
    signals = [s for s in signals_for("run_sig") if s.kind == "membrane_rejection"]
    assert len(signals) == 1
    assert signals[0].value == pytest.approx(0.5)


# --------------------------------------------------------------------------
# The money-shot: an adversarial input cannot change a verdict
# --------------------------------------------------------------------------


def test_injection_heuristic_fires_on_the_seeded_log():
    scan = scan_for_injection(seed_text("injected_log.txt"))
    assert scan.suspicious
    assert "override_instructions" in scan.matched
    assert "verdict_steering" in scan.matched
    assert scan.excerpts


def test_clean_text_does_not_trip_the_heuristic():
    assert not scan_for_injection(
        "[11:00 IST] act_1 RETRY mandate mdt_1 cust cus_1 amt Rs.1,499 attempt 2"
    ).suspicious


def test_a_fully_hijacked_parser_cannot_produce_a_pass(pack):
    """The architecture money-shot, as a test.

    Simulate the worst case: the injection succeeds completely and the ingestion agent
    returns actions decorated with a fabricated compliant verdict. The membrane rejects
    the fabrications, and the actions that *are* schema-valid are judged by the core on
    their facts — the injected instruction never reaches the verdict path at all.
    """
    hijacked = [
        # what a hijacked model might emit: a verdict it was told to assert
        {
            "id": "a_v03", "type": "debit", "timestamp": "2026-08-20T15:00:00+05:30",
            "amount": 20000.0, "afa_present": False,
            "notice_sent_at": "2026-08-18T15:00:00+05:30",
            "debit_due_at": "2026-08-20T15:00:00+05:30",
            "verdict": "compliant", "violations": [],
        },
        # and the same action without the fabrication
        {
            "id": "a_v03b", "type": "debit", "timestamp": "2026-08-20T15:00:00+05:30",
            "amount": 20000.0, "afa_present": False,
            "notice_sent_at": "2026-08-18T15:00:00+05:30",
            "debit_due_at": "2026-08-20T15:00:00+05:30",
        },
    ]
    result = validate_membrane_detailed(hijacked, "run_hijack")

    assert len(result.rejections) == 1, "the fabricated verdict fields must be rejected"
    assert [a.id for a in result.actions] == ["a_v03b"]

    violations = evaluate(result.actions, pack)
    assert [v.rule_id for v in violations] == ["AFA_ABOVE_THRESHOLD"], (
        "the core judged the facts; the injected 'compliant' claim changed nothing"
    )
