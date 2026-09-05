"""Rule-pack loading + validation — 02-system-design.md §A.2/§A.3.

Rules are a versioned, inspectable artifact, not code (invariant I4). The condition
vocabulary is a *closed set* (invariant I6): a pack naming an unknown `kind` fails to
load rather than being silently ignored, because a silently-skipped rule is a false PASS.

Pack composition
----------------
A pack file is **primary** iff it declares `circular:` — it carries the regulation the
report cites, and its `version` *is* the rule-pack version. Non-primary files (NPCI
operational guidelines) merge into whichever primary version is selected. This is what
makes "re-verify last month's log under the April rules" a directory-level operation:
drop in a new primary file, and its version appears in /rules/versions.

This module is part of the deterministic core: no LLM, no network, no config import.
"""

from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.core.models import Action, ActionType, MandateCategory, Severity

DEFAULT_RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


class RulePackError(Exception):
    """Malformed pack, unknown condition kind, or unknown version."""


# --------------------------------------------------------------------------
# Condition vocabulary — closed set. One model + one evaluator per kind.
# --------------------------------------------------------------------------


class HoursBetweenAtLeast(BaseModel):
    kind: Literal["hours_between_at_least"]
    earlier: str
    later: str
    hours: float


class IfAmountGtThenFlag(BaseModel):
    kind: Literal["if_amount_gt_then_flag"]
    amount_field: str
    threshold: float
    required_flag: str


class MaxValue(BaseModel):
    kind: Literal["max_value"]
    field: str
    max: float


class FlagMustBeFalse(BaseModel):
    kind: Literal["flag_must_be_false"]
    field: str


class TimestampHourBetween(BaseModel):
    kind: Literal["timestamp_hour_between"]
    field: str
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=0, le=24)


Condition = Annotated[
    Union[
        HoursBetweenAtLeast,
        IfAmountGtThenFlag,
        MaxValue,
        FlagMustBeFalse,
        TimestampHourBetween,
    ],
    Field(discriminator="kind"),
]

CONDITION_KINDS = {
    "hours_between_at_least",
    "if_amount_gt_then_flag",
    "max_value",
    "flag_must_be_false",
    "timestamp_hour_between",
}

# Which keys of each condition name an `Action` field rather than carrying a literal.
#
# The closed vocabulary already stops a rule naming a condition *kind* the engine cannot
# evaluate. It did not stop a rule naming a *field* the Action does not have, and that gap
# is not cosmetic: every evaluator reads its operands with `getattr(action, name, None)`,
# so a typo'd or invented field resolves to None for every action forever. Under
# `if_amount_gt_then_flag` a missing required_flag reads as "the flag is not set", which
# fails every action above the threshold and reports the reason as `AFA=missing` — a rule
# that silently flags compliant behaviour, which is the worst failure this tool has.
#
# Found by drafting a rule with the model: it proposed `required_flag: AFA` where the field
# is `afa_present`, and the pack accepted it. Checking the names closes the authoring path
# the same way the vocabulary closes the evaluation path.
CONDITION_FIELD_REFS: dict[str, tuple[str, ...]] = {
    "hours_between_at_least": ("earlier", "later"),
    "if_amount_gt_then_flag": ("amount_field", "required_flag"),
    "max_value": ("field",),
    "flag_must_be_false": ("field",),
    "timestamp_hour_between": ("field",),
}

ACTION_FIELDS = frozenset(Action.model_fields)


# --------------------------------------------------------------------------
# Rules + exemptions
# --------------------------------------------------------------------------


class Rule(BaseModel):
    id: str
    title: str
    applies_to: list[ActionType]
    severity: Severity
    clause: str
    condition: Condition
    source: str = ""  # injected from the owning pack file
    value_verified: bool = False
    # The date a human checked this value against the cited clause. Declared rather than
    # left to a YAML comment so it survives into /rules and the dashboard — "who checked
    # this, and when" is part of the audit trail, not metadata about it.
    verified_on: Optional[str] = None
    # Where the clause was read. "Verified on 2026-09-05" is unfalsifiable on its own; a
    # URL is what lets a reviewer repeat the check instead of taking our word for it, which
    # is the same standard `clause_text` sets for the wording.
    verified_against: Optional[str] = None
    # The cited clause, verbatim. A citation nobody can check is an assertion; carrying
    # the sentence itself turns "trust our reading of §8(a)" into "here is §8(a)". It is
    # display-only and can never reach a verdict — the condition above decides, and this
    # is the evidence a reviewer reads to confirm the condition matches the law.
    clause_text: Optional[str] = None


class Exemption(BaseModel):
    """Suppresses listed rules for actions matching every selector it declares.

    Three selectors, all optional individually but at least one required overall:
    `when_mcc_in`, `when_category_in`, and `max_amount`. Present selectors are ANDed —
    §8(b) of the 2026 framework needs exactly that shape, since its waiver applies to
    three named categories *and* only up to ₹1,00,000. An exemption with no selector at
    all would suppress its rules unconditionally, which is a false PASS, so the pack
    fails to load rather than defaulting to permissive (invariant I6's reasoning applied
    to exemptions).
    """

    id: str
    title: str
    exempts: list[str]
    when_mcc_in: list[str] = Field(default_factory=list)
    when_category_in: list[MandateCategory] = Field(default_factory=list)
    max_amount: Optional[float] = None
    clause: str
    source: str = ""
    value_verified: bool = False
    verified_on: Optional[str] = None
    verified_against: Optional[str] = None
    clause_text: Optional[str] = None

    @model_validator(mode="after")
    def _requires_a_selector(self) -> "Exemption":
        if not self.when_mcc_in and not self.when_category_in and self.max_amount is None:
            raise ValueError(
                f"exemption {self.id!r} declares no selector; it would suppress "
                f"{self.exempts} for every action"
            )
        return self

    def covers(self, rule_id: str, action: Action) -> bool:
        if rule_id not in self.exempts:
            return False
        if self.when_mcc_in and (action.mcc is None or action.mcc not in self.when_mcc_in):
            return False
        if self.when_category_in and (
            action.category is None or action.category not in self.when_category_in
        ):
            return False
        if self.max_amount is not None and (
            action.amount is None or action.amount > self.max_amount
        ):
            return False
        return True


class ExemptionSet(BaseModel):
    exemptions: list[Exemption] = Field(default_factory=list)

    def suppresses(self, rule_id: str, action: Action) -> Optional[Exemption]:
        """Return the exemption suppressing `rule_id` for `action`, else None."""
        for ex in self.exemptions:
            if ex.covers(rule_id, action):
                return ex
        return None


class PackSource(BaseModel):
    """Provenance of one contributing YAML file — surfaced by GET /rules."""

    file: str
    version: str
    source: str
    circular: Optional[str] = None
    effective_from: Optional[date] = None
    primary: bool = False
    # When a human last confirmed the cited circular is still in force. This pack cites
    # paragraph numbers in one specific document, and RBI/DPSS/2026-27/396 itself repealed
    # eight earlier circulars — so a pack can become confidently wrong without anything in
    # it changing. `scripts/check_circulars.py` refreshes this; /health reports its age.
    circular_checked_on: Optional[date] = None


class RulePack(BaseModel):
    version: str
    sources: list[PackSource] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    exemptions: list[Exemption] = Field(default_factory=list)

    @property
    def source(self) -> str:
        """The primary regulation this pack is named for."""
        for s in self.sources:
            if s.primary:
                return s.source
        return self.sources[0].source if self.sources else ""

    @property
    def circular(self) -> Optional[str]:
        for s in self.sources:
            if s.primary:
                return s.circular
        return None

    def rules_for(self, action_type: ActionType) -> list[Rule]:
        return [r for r in self.rules if action_type in r.applies_to]

    def exemptions_for(self, actions: list[Action]) -> ExemptionSet:
        # Signature mirrors the design doc; the set is action-independent today, but
        # keeping `actions` in the signature leaves room for time-bounded exemptions
        # without changing the engine.
        return ExemptionSet(exemptions=self.exemptions)

    def unverified_values(self) -> list[str]:
        """Rule ids still carrying an unconfirmed regulatory value (OPEN-2)."""
        return [r.id for r in self.rules if not r.value_verified] + [
            e.id for e in self.exemptions if not e.value_verified
        ]


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def _parse_file(path: Path) -> tuple[PackSource, list[Rule], list[Exemption]]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RulePackError(f"{path.name}: invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise RulePackError(f"{path.name}: top level must be a mapping")
    for key in ("version", "source", "rules"):
        if key not in raw:
            raise RulePackError(f"{path.name}: missing required key '{key}'")
    if not isinstance(raw["rules"], list) or not raw["rules"]:
        raise RulePackError(f"{path.name}: 'rules' must be a non-empty list")

    meta = PackSource(
        file=path.name,
        version=str(raw["version"]),
        source=str(raw["source"]),
        circular=raw.get("circular"),
        effective_from=raw.get("effective_from"),
        primary="circular" in raw,
        circular_checked_on=raw.get("circular_checked_on"),
    )

    rules: list[Rule] = []
    exemptions: list[Exemption] = []
    for entry in raw["rules"]:
        if not isinstance(entry, dict) or "id" not in entry:
            raise RulePackError(f"{path.name}: every rule needs an 'id'")
        # Pack source is the default, not an override. A pack collects rules by *where they
        # are maintained*, which is not always where they come from: QUIET_HOURS lives in
        # the NPCI pack but is an RBI Fair Practices Code rule, and stamping NPCI on it
        # would misattribute the law. A rule that names its own source keeps it.
        entry = {"source": meta.source, **entry}

        if entry.get("kind") == "exemption":
            try:
                exemptions.append(Exemption.model_validate(entry))
            except ValidationError as exc:
                raise RulePackError(f"{path.name}: exemption {entry['id']}: {exc}") from exc
            continue

        cond = entry.get("condition")
        if not isinstance(cond, dict) or "kind" not in cond:
            raise RulePackError(f"{path.name}: rule {entry['id']}: missing condition.kind")
        if cond["kind"] not in CONDITION_KINDS:
            raise RulePackError(
                f"{path.name}: rule {entry['id']}: unknown condition kind "
                f"'{cond['kind']}'. Closed vocabulary is {sorted(CONDITION_KINDS)}"
            )
        # Every operand must name a real Action field. Failing the load is the only safe
        # option: the evaluators read operands with getattr(..., None), so an unknown name
        # does not error at verdict time — it quietly resolves to None for every action and
        # turns the rule into a false-positive generator (invariant I6's reasoning: fail to
        # load rather than default to a permissive, or here an over-strict, reading).
        for key in CONDITION_FIELD_REFS[cond["kind"]]:
            name = cond.get(key)
            if isinstance(name, str) and name not in ACTION_FIELDS:
                raise RulePackError(
                    f"{path.name}: rule {entry['id']}: condition.{key} names "
                    f"'{name}', which is not a field on Action. "
                    f"Known fields are {sorted(ACTION_FIELDS)}"
                )
        try:
            rules.append(Rule.model_validate(entry))
        except ValidationError as exc:
            raise RulePackError(f"{path.name}: rule {entry['id']}: {exc}") from exc

    return meta, rules, exemptions


def _scan(rules_dir: Path) -> list[tuple[PackSource, list[Rule], list[Exemption]]]:
    if not rules_dir.is_dir():
        raise RulePackError(f"rules directory not found: {rules_dir}")
    files = sorted(p for p in rules_dir.iterdir() if p.suffix in (".yaml", ".yml"))
    if not files:
        raise RulePackError(f"no rule-pack files in {rules_dir}")
    return [_parse_file(p) for p in files]


def available_versions(rules_dir: Path = DEFAULT_RULES_DIR) -> list[str]:
    """Versions selectable as ACTIVE_RULEPACK — one per primary pack file."""
    return sorted({meta.version for meta, _, _ in _scan(rules_dir) if meta.primary})


def load_pack(version: Optional[str] = None, rules_dir: Path = DEFAULT_RULES_DIR) -> RulePack:
    """Compose the pack for `version` (default: the only/latest primary version)."""
    parsed = _scan(rules_dir)
    primaries = {meta.version: item for item in parsed if (meta := item[0]).primary}
    if not primaries:
        raise RulePackError(
            f"no primary rule-pack in {rules_dir} — exactly one file must declare 'circular:'"
        )

    if version is None:
        version = sorted(primaries)[-1]
    if version not in primaries:
        raise RulePackError(
            f"unknown rulepack_version '{version}'. Available: {sorted(primaries)}"
        )

    meta, rules, exemptions = primaries[version]
    sources, all_rules, all_exemptions = [meta], list(rules), list(exemptions)

    for other_meta, other_rules, other_exemptions in parsed:
        if other_meta.primary:
            continue
        sources.append(other_meta)
        all_rules.extend(other_rules)
        all_exemptions.extend(other_exemptions)

    seen: set[str] = set()
    for r in all_rules + all_exemptions:  # type: ignore[operator]
        if r.id in seen:
            raise RulePackError(f"duplicate rule id '{r.id}' across pack files")
        seen.add(r.id)

    return RulePack(version=version, sources=sources, rules=all_rules, exemptions=all_exemptions)
