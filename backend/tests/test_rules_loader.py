"""Rule-pack loading, validation, versioning and exemption suppression."""

from pathlib import Path

import pytest

from app.core.models import ActionType
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
        "PRE_DEBIT_NOTICE_24H", "AFA_ABOVE_THRESHOLD", "NO_RETRY_UNDER_DISPUTE"
    }
    assert pack.rules_for(ActionType.ESCALATE) == []


def test_unverified_values_are_reported(pack):
    """OPEN-2 must stay visible, not silently ship.

    As of 2026-09-02 the RBI values were read in the circular itself and are verified;
    the two remaining entries rest on secondary sourcing only. That distinction is the
    whole point of the flag, so this test pins *which* values are still unverified
    rather than merely that some are.
    """
    unverified = pack.unverified_values()
    assert "RETRY_CAP_PER_WINDOW" in unverified, "NPCI circular not read in primary form"
    assert "QUIET_HOURS" in unverified, "Fair Practices Code not read in primary form"
    assert "AFA_ABOVE_THRESHOLD" not in unverified, "verified against §8(a)"
    assert "PRE_DEBIT_NOTICE_24H" not in unverified, "verified against §6(a)"


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
