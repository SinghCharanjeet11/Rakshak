"""Rule-pack loading, validation, versioning and exemption suppression."""

from pathlib import Path

import pytest

from app.core.models import Action, ActionType
from app.core.rules_loader import (
    RulePackError,
    available_versions,
    load_pack,
)
from tests.conftest import make_action

VALID_PRIMARY = """
version: "9999.01-1"
source: "Test Regulator"
circular: "TEST/9999/1"
effective_from: "9999-01-01"
rules:
  - id: TEST_RULE
    title: "Amount must not exceed 100"
    applies_to: [debit]
    severity: low
    clause: "TEST §1"
    condition: {kind: max_value, field: amount, max: 100}
"""


def _write(tmp_path: Path, name: str, body: str) -> Path:
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_the_shipped_pack_loads(pack):
    assert pack.version == "2026.04.21-1"
    assert pack.circular == "RBI/DPSS/2026-27/396"
    assert {r.id for r in pack.rules} == {
        "PRE_DEBIT_NOTICE_24H",
        "AFA_ABOVE_THRESHOLD",
        "NO_DEBIT_AFTER_OPT_OUT",
        "RETRY_CAP_PER_WINDOW",
        "NO_RETRY_UNDER_DISPUTE",
        "RESPECT_OPT_OUT",
        "QUIET_HOURS",
    }
    assert {e.id for e in pack.exemptions} == {
        "EXEMPT_MCC_SKIP_NOTICE",
        "EXEMPT_HIGH_VALUE_CATEGORY_AFA",
    }


def test_every_rule_carries_a_clause_and_source(pack):
    """Invariant I5 starts at load time: a rule with no citation cannot cite one later."""
    for rule in pack.rules:
        assert rule.clause and rule.source
    for ex in pack.exemptions:
        assert ex.clause and ex.source


def test_rules_for_filters_by_action_type(pack):
    debit_rules = {r.id for r in pack.rules_for(ActionType.DEBIT)}
    assert debit_rules == {
        "PRE_DEBIT_NOTICE_24H",
        "AFA_ABOVE_THRESHOLD",
        "NO_RETRY_UNDER_DISPUTE",
        "NO_DEBIT_AFTER_OPT_OUT",
    }
    assert pack.rules_for(ActionType.ESCALATE) == []


def test_unverified_values_are_reported(pack):
    """OPEN-2 must stay visible, not silently ship.

    The RBI e-mandate values were read in the circular itself on 2026-09-02 and re-read
    against rbi.org.in on 2026-09-05; QUIET_HOURS was verified on 2026-09-05 once its
    primary instrument was located. What remains unverified rests on sourcing that is
    corroborated but not quoted. That distinction is the whole point of the flag, so this
    test pins *which* values are still unverified rather than merely that some are.
    """
    unverified = pack.unverified_values()
    assert "RETRY_CAP_PER_WINDOW" in unverified, "NPCI circular is not published openly"
    assert "NO_RETRY_UNDER_DISPUTE" in unverified, "no primary source located"
    assert "QUIET_HOURS" not in unverified, "verified against RBI/2022-23/108 ¶2"
    assert "AFA_ABOVE_THRESHOLD" not in unverified, "verified against §8(a)"
    assert "PRE_DEBIT_NOTICE_24H" not in unverified, "verified against §6(a)"


def test_a_verified_rule_says_where_it_was_read(pack):
    """`verified_on` alone is unfalsifiable — a date with no document behind it. Anything
    claiming verification has to carry the source it was read at, so a reviewer can repeat
    the check instead of trusting the flag."""
    for r in pack.rules:
        if r.value_verified:
            assert r.verified_on, f"{r.id}: verified with no date"
            assert r.verified_against, f"{r.id}: verified with no readable source"
            assert r.verified_against.startswith("http"), f"{r.id}: source is not a URL"
            assert r.clause_text, f"{r.id}: verified but does not carry the clause wording"
            assert "NOT QUOTED" not in r.clause_text.upper(), (
                f"{r.id}: flagged verified while its clause_text still says it is not quoted"
            )


def test_quiet_hours_is_attributed_to_rbi_not_npci(pack):
    """It lives in the NPCI pack because that is where conduct rules are maintained, but
    the obligation is RBI's. Inheriting the pack's source would misattribute the law."""
    rule = next(r for r in pack.rules if r.id == "QUIET_HOURS")
    assert "RBI" in rule.source and "NPCI" not in rule.source
    assert "RBI/2022-23/108" in rule.clause
    assert "8:00 a.m." in rule.clause_text and "7:00 p.m." in rule.clause_text


def test_a_condition_naming_an_unknown_action_field_fails_to_load(tmp_path):
    """The regression that motivated the check, taken from a real drafted rule.

    Asked to encode a cross-border AFA clause, the drafting agent proposed
    `required_flag: AFA` where the field is `afa_present`. Nothing rejected it: the
    condition *kind* was valid, so the pack loaded.

    That is not a cosmetic typo. Evaluators read operands with `getattr(action, name, None)`,
    so an unknown name resolves to None for every action — and under this condition kind a
    None flag reads as "not set", failing every debit above the threshold and citing
    `AFA=missing`. A rule that flags compliant behaviour is the worst output this tool can
    produce, and it would have arrived looking exactly like a working rule.
    """
    bad = VALID_PRIMARY.replace(
        "condition: {kind: max_value, field: amount, max: 100}",
        "condition: {kind: if_amount_gt_then_flag, amount_field: amount, "
        "threshold: 5000, required_flag: AFA}",
    )
    _write(tmp_path, "bad.yaml", bad)
    with pytest.raises(RulePackError) as exc:
        load_pack("9999.01-1", tmp_path)
    assert "required_flag" in str(exc.value)
    assert "AFA" in str(exc.value)
    assert "afa_present" in str(exc.value), "the error should name the fields that do exist"


@pytest.mark.parametrize(
    "condition",
    [
        "{kind: max_value, field: nonexistent, max: 4}",
        "{kind: flag_must_be_false, field: nonexistent}",
        "{kind: timestamp_hour_between, field: nonexistent, start_hour: 8, end_hour: 19}",
        "{kind: hours_between_at_least, earlier: nonexistent, later: debit_due_at, hours: 24}",
        "{kind: hours_between_at_least, earlier: notice_sent_at, later: nonexistent, hours: 24}",
    ],
)
def test_every_condition_kind_checks_its_field_operands(tmp_path, condition):
    """Each kind reads different operand keys, so each needs covering — a check that only
    caught `if_amount_gt_then_flag` would leave the same hole open four ways."""
    _write(
        tmp_path,
        "bad.yaml",
        VALID_PRIMARY.replace(
            "condition: {kind: max_value, field: amount, max: 100}",
            f"condition: {condition}",
        ),
    )
    with pytest.raises(RulePackError, match="not a field on Action"):
        load_pack("9999.01-1", tmp_path)


def test_the_shipped_pack_only_references_real_action_fields(pack):
    """Belt and braces on the pack that actually ships, independent of the loader check."""
    from app.core.rules_loader import ACTION_FIELDS, CONDITION_FIELD_REFS

    for rule in pack.rules:
        cond = rule.condition.model_dump()
        for key in CONDITION_FIELD_REFS[cond["kind"]]:
            assert cond[key] in ACTION_FIELDS, f"{rule.id}: condition.{key}={cond[key]!r}"


def test_available_versions_lists_primary_packs():
    assert "2026.04.21-1" in available_versions()


def test_unknown_version_raises():
    with pytest.raises(RulePackError, match="unknown rulepack_version"):
        load_pack("1999.01-1")


def test_version_selection_picks_the_right_primary(tmp_path):
    _write(tmp_path, "a.yaml", VALID_PRIMARY)
    _write(tmp_path, "b.yaml", VALID_PRIMARY.replace("9999.01-1", "9999.02-1"))

    assert sorted(available_versions(tmp_path)) == ["9999.01-1", "9999.02-1"]
    assert load_pack("9999.02-1", tmp_path).version == "9999.02-1"


def test_non_primary_packs_merge_into_the_selected_version(tmp_path):
    _write(tmp_path, "primary.yaml", VALID_PRIMARY)
    _write(
        tmp_path,
        "ops.yaml",
        """
version: "ops-1"
source: "Ops Guideline"
rules:
  - id: OPS_RULE
    title: "No dispute retries"
    applies_to: [mandate_retry]
    severity: high
    clause: "OPS §1"
    condition: {kind: flag_must_be_false, field: dispute_active}
""",
    )
    loaded = load_pack("9999.01-1", tmp_path)
    assert {r.id for r in loaded.rules} == {"TEST_RULE", "OPS_RULE"}
    assert loaded.source == "Test Regulator"  # the primary names the pack


def test_malformed_yaml_raises(tmp_path):
    _write(tmp_path, "bad.yaml", "version: [unclosed\n")
    with pytest.raises(RulePackError, match="invalid YAML"):
        load_pack(None, tmp_path)


def test_missing_required_key_raises(tmp_path):
    _write(tmp_path, "bad.yaml", 'version: "1"\nsource: "X"\ncircular: "C"\n')
    with pytest.raises(RulePackError, match="missing required key 'rules'"):
        load_pack(None, tmp_path)


def test_unknown_condition_kind_raises(tmp_path):
    """Invariant I6: the vocabulary is closed. A silently-skipped rule is a false PASS."""
    _write(
        tmp_path,
        "bad.yaml",
        VALID_PRIMARY.replace(
            "{kind: max_value, field: amount, max: 100}",
            "{kind: vibes_based_check, field: amount}",
        ),
    )
    with pytest.raises(RulePackError, match="unknown condition kind"):
        load_pack(None, tmp_path)


def test_condition_with_wrong_fields_raises(tmp_path):
    _write(
        tmp_path,
        "bad.yaml",
        VALID_PRIMARY.replace(
            "{kind: max_value, field: amount, max: 100}", "{kind: max_value, field: amount}"
        ),
    )
    with pytest.raises(RulePackError):
        load_pack(None, tmp_path)


def test_duplicate_rule_id_across_files_raises(tmp_path):
    _write(tmp_path, "primary.yaml", VALID_PRIMARY)
    _write(
        tmp_path,
        "dup.yaml",
        """
version: "ops-1"
source: "Ops"
rules:
  - id: TEST_RULE
    title: "Duplicate"
    applies_to: [debit]
    severity: low
    clause: "OPS §1"
    condition: {kind: max_value, field: amount, max: 5}
""",
    )
    with pytest.raises(RulePackError, match="duplicate rule id"):
        load_pack("9999.01-1", tmp_path)


def test_pack_with_no_primary_raises(tmp_path):
    _write(
        tmp_path,
        "ops.yaml",
        """
version: "ops-1"
source: "Ops"
rules:
  - id: R
    title: "t"
    applies_to: [debit]
    severity: low
    clause: "c"
    condition: {kind: max_value, field: amount, max: 5}
""",
    )
    with pytest.raises(RulePackError, match="no primary rule-pack"):
        load_pack(None, tmp_path)


def test_empty_rules_directory_raises(tmp_path):
    with pytest.raises(RulePackError, match="no rule-pack files"):
        load_pack(None, tmp_path)


def test_exemption_suppression(pack):
    fastag = make_action(mcc="4784")
    other = make_action(mcc="5411")
    none_set = make_action()

    exemptions = pack.exemptions_for([fastag])
    assert exemptions.suppresses("PRE_DEBIT_NOTICE_24H", fastag) is not None
    assert exemptions.suppresses("PRE_DEBIT_NOTICE_24H", other) is None
    assert exemptions.suppresses("PRE_DEBIT_NOTICE_24H", none_set) is None
    assert exemptions.suppresses("AFA_ABOVE_THRESHOLD", fastag) is None


def test_unsubstantiated_ncmc_mcc_is_not_exempt(pack):
    """MCC 7412 was removed on 2026-09-02 — it has no basis in RBI/DPSS/2026-27/396.

    §6(d) exempts by purpose ("e-mandates registered to auto-replenish balances of
    FASTag, and NCMC") and names no MCC at all. 4784 is kept as a defensible proxy for
    FASTag tolls; 7412 was researched, never substantiated, and an exemption is the one
    kind of rule where being wrong produces a false PASS.
    """
    ncmc = make_action(mcc="7412")
    assert pack.exemptions_for([ncmc]).suppresses("PRE_DEBIT_NOTICE_24H", ncmc) is None


def test_high_value_category_is_exempt_from_afa_up_to_one_lakh(pack):
    """§8(b): insurance / mutual fund / credit card bill need no AFA up to ₹1,00,000."""
    premium = make_action(type="debit", amount=50000.0, category="insurance_premium")
    over_cap = make_action(type="debit", amount=150000.0, category="insurance_premium")
    uncategorised = make_action(type="debit", amount=50000.0)

    ex = pack.exemptions_for([premium, over_cap, uncategorised])
    assert ex.suppresses("AFA_ABOVE_THRESHOLD", premium) is not None
    assert ex.suppresses("AFA_ABOVE_THRESHOLD", over_cap) is None, "the ₹1L cap still binds"
    assert ex.suppresses("AFA_ABOVE_THRESHOLD", uncategorised) is None
    assert ex.suppresses("PRE_DEBIT_NOTICE_24H", premium) is None, "waives AFA only"


def test_verified_rules_carry_the_clause_text_they_cite(pack):
    """A citation nobody can check is an assertion.

    Every value marked verified was read in the circular, so the sentence it was read
    from must travel with it. This is what lets a reviewer confirm the condition matches
    the law instead of taking our word for the paragraph number.
    """
    for item in list(pack.rules) + list(pack.exemptions):
        if item.value_verified and item.clause.startswith("RBI/DPSS/2026-27/396"):
            assert item.clause_text, f"{item.id} cites {item.clause} but quotes nothing"
            assert len(item.clause_text) > 40, f"{item.id} clause_text looks truncated"


def test_unverified_rules_say_so_in_their_clause_text(pack):
    """A secondary-sourced value must not read like quoted law.

    The disclaimer wording varies by how much is actually known — an instrument that has
    been identified but not obtained says something different from one with no primary
    source at all — so this pins the claim ("not quoted") rather than one exact sentence.
    The failure it guards against is an unverified value silently acquiring the authority
    of a verbatim citation.
    """
    for rule in pack.rules:
        if not rule.value_verified and rule.clause_text:
            assert "NOT QUOTED" in rule.clause_text.upper(), (
                f"{rule.id}: unverified but its clause_text does not say it is unquoted"
            )


def test_clause_text_cannot_reach_a_verdict():
    """Invariant I8's reasoning applied to provenance: it is evidence, never input.

    Blanking every clause_text must not change a single verdict.

    Loads its own pack rather than taking the session fixture, because this test mutates
    what it is given and the fixture is shared for the whole run.
    """
    import json
    from pathlib import Path

    from app.core.rule_engine import evaluate

    seed = Path(__file__).resolve().parent.parent / "app" / "seed" / "violating_actions.json"
    actions = [Action.model_validate(a) for a in json.loads(seed.read_text(encoding="utf-8"))]

    scratch = load_pack("2026.04.21-1")
    before = {(v.action_id, v.rule_id) for v in evaluate(actions, scratch)}
    for item in list(scratch.rules) + list(scratch.exemptions):
        item.clause_text = None
    after = {(v.action_id, v.rule_id) for v in evaluate(actions, scratch)}
    assert before == after
