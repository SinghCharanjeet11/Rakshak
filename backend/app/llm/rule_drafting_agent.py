"""Rule-drafting subagent — regulation text -> a proposed rule-pack entry.

The maintenance answer
---------------------
The one real objection to a rule engine is "who maintains this when the regulator amends
the framework?". Until now the answer was "a person, by hand": on 2026-09-02 someone read
RBI/DPSS/2026-27/396 and hand-wrote YAML for §6(a), §8(a), §6(d), §8(b) and §6(c). That is
a mechanical translation, and mechanical translation is what a model is for.

The answer becomes: **the model drafts, a human approves, and the committed artifact stays
deterministic data.**

Why this cannot corrupt a verdict
---------------------------------
Its output is not a verdict and never becomes one. It is *data that a human reviews and
the engine later applies*, which is the test `07-ai-workflow.md` sets for any new use of
AI here: can this output change a PASS/FAIL? No — nothing in this module writes to a
rule-pack, and `draft_rule` returns a proposal, never a committed rule.

It also crosses a membrane, and deliberately the *same* one the rules already have: the
condition vocabulary is a closed set of six kinds, so a model that invents
`kind: vibes_based_check` is rejected by `Rule.model_validate` exactly as a hallucinated
field on an `Action` is rejected at ingestion. The pattern that protects the verdict path
protects the authoring path too, without a second mechanism being invented for it.

Zero tools, like the explainer. The only input it ever sees is clause text a human pasted.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from app.core.rules_loader import CONDITION_KINDS, Exemption, Rule
from app.llm._provider import LLMResponse, LLMUnavailable, Usage, complete_json

log = logging.getLogger("rakshak.llm.draft")

# Zero tools. Asserted by tests/test_least_privilege.py, like the explainer.
DRAFTING_TOOLS: list[dict[str, Any]] = []

# The closed vocabulary, spelled out for the model. Kept generated from CONDITION_KINDS so
# it cannot drift from what rules_loader will actually accept.
_CONDITION_SHAPES = """\
  hours_between_at_least  {"kind","earlier","later","hours"}
      earlier/later are Action field names; use for "X must precede Y by N hours".
  if_amount_gt_then_flag  {"kind","amount_field","threshold","required_flag"}
      use for "above <amount>, <flag> is required". Strictly greater than threshold.
  max_value               {"kind","field","max"}
      use for "no more than N". The value itself is permitted; N+1 is the breach.
  flag_must_be_false      {"kind","field"}
      use for "do not do X when <flag>".
  timestamp_hour_between  {"kind","field","start_hour","end_hour"}
      use for "only between HH:00 and HH:00 IST". 24-hour clock, IST.\
"""

def _action_fields() -> str:
    """The Action field names a condition may reference, generated from the model itself.

    Not hand-written: the first live run had the drafter inventing field names out of the
    regulation's prose ("pre-transaction notification" rather than `notice_sent_at`),
    because nothing told it what an Action actually carries. A hand-maintained list would
    drift from the schema the moment a field is added.
    """
    from app.core.models import Action

    skip = {"id", "type", "currency"}
    return ", ".join(sorted(f for f in Action.model_fields if f not in skip))


DRAFTING_SYSTEM = f"""\
You translate a passage of financial regulation into ONE entry for a compliance rule-pack.

You are drafting a proposal for a human to review. You are not deciding anything, and no \
verdict depends on your output.

The condition vocabulary is CLOSED. You may use only these five kinds, with exactly these \
fields:
{_CONDITION_SHAPES}

The condition MUST be nested under the key "condition", and "condition" MUST contain a \
"kind" key. Do not name the key after the kind.

Every field name inside a condition MUST be one of these exact Action fields. Never invent \
a field name, and never use a phrase from the regulation as a field name:
  {_action_fields()}

If the passage needs a fact none of those fields carries, do not approximate it with a \
different field. Return drafted:false and say which fact is missing -- a rule pointed at \
the wrong field silently checks the wrong thing, which is worse than no rule.

"applies_to" is always a LIST, even with one entry.

If the passage cannot be expressed in that vocabulary, say so instead of inventing a kind: \
return {{"drafted": false, "reason": "<why>"}}. An honest refusal is useful; an invented \
condition kind is rejected on load and wastes a reviewer's time.

Rules for the fields you produce:
- `id`: SCREAMING_SNAKE_CASE, specific, e.g. PRE_DEBIT_NOTICE_24H.
- `title`: one line a compliance officer would recognise.
- `applies_to`: any of debit, mandate_retry, notify, contact, escalate.
- `severity`: critical, high, medium or low. Reserve critical for a breach that harms a \
customer's money or consent.
- `clause`: the citation exactly as it appears, e.g. "RBI/DPSS/2026-27/396 §8(a)".
- `clause_text`: the passage VERBATIM. Do not paraphrase, summarise or tidy it. A reviewer \
compares this against the condition to decide whether you read the law correctly.
- Never set `value_verified`. A human decides that after checking, not you.

Watch for carve-outs. A threshold in one sub-clause is very often qualified by an exception \
in the next one, and a rule that encodes the threshold while missing the exception reports \
lawful behaviour as a breach.

Return a JSON object:
  {{"drafted": true, "kind": "rule", "rule": {{...}}}}
or for an exemption that suppresses other rules:
  {{"drafted": true, "kind": "exemption", "exemption": {{"id","title","exempts":[...],\
"when_mcc_in":[...],"when_category_in":[...],"max_amount":N,"clause","clause_text"}}}}
or:
  {{"drafted": false, "reason": "..."}}\
"""


class DraftResult(BaseModel):
    """Outcome of one drafting attempt.

    `accepted` means the proposal survived `Rule`/`Exemption` validation, not that it is
    correct. Correctness is a human's judgement and is what the review screen is for.
    """

    drafted: bool = False
    accepted: bool = False
    kind: Optional[str] = None
    rule: Optional[Rule] = None
    exemption: Optional[Exemption] = None
    yaml: Optional[str] = None
    reason: Optional[str] = None
    rejection: Optional[str] = None
    raw: dict[str, Any] = Field(default_factory=dict)
    usage: Usage = Field(default_factory=Usage)


def _to_yaml(payload: dict[str, Any], is_exemption: bool) -> str:
    """Render the proposal as pack YAML a reviewer can paste after checking it.

    Hand-rolled rather than yaml.dump so the key order matches the existing packs and the
    output is diffable against them; a dumper would sort keys and produce a diff that
    obscures what actually changed.
    """
    def _scalar(v: Any) -> str:
        """Render one value for the pack.

        Not yaml.safe_dump: for a bare scalar it emits a `...` document-end marker, which
        ended up interleaved through the first drafts as stray lines.
        """
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, list):
            return "[" + ", ".join(str(x) for x in v) + "]"
        text = str(v)
        return f'"{text}"' if (":" in text or text.strip() != text) else text

    order = (
        ["id", "title", "exempts", "when_mcc_in", "when_category_in", "max_amount",
         "clause", "clause_text"]
        if is_exemption
        else ["id", "title", "applies_to", "severity", "clause", "clause_text", "condition"]
    )
    lines = ["  - " + ("kind: exemption" if is_exemption else f"id: {payload['id']}")]
    if is_exemption:
        lines = [f"  - id: {payload['id']}", "    kind: exemption"]

    for key in order:
        if key == "id" or key not in payload or payload[key] in (None, [], {}):
            continue
        value = payload[key]
        if key == "clause_text":
            lines.append("    clause_text: >-")
            for chunk in _wrap(str(value), 84):
                lines.append(f"      {chunk}")
        elif key == "condition":
            lines.append("    condition:")
            for k, v in value.items():
                lines.append(f"      {k}: {_scalar(v)}")
        else:
            lines.append(f"    {key}: {_scalar(value)}")

    lines.append("    # value_verified intentionally omitted: a human sets it after checking.")
    return "\n".join(lines)


def _wrap(text: str, width: int) -> list[str]:
    words, out, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return out


def validate_draft(raw: dict[str, Any]) -> DraftResult:
    """The membrane for authored rules.

    Pure and synchronous, so it is testable without a model: hand it what a compromised
    model might return and assert the pack cannot be poisoned. Same posture as the action
    membrane -- rejection is conservative and reported, never silently downgraded.
    """
    if not isinstance(raw, dict):
        return DraftResult(rejection="model returned a non-object")

    if not raw.get("drafted"):
        return DraftResult(
            drafted=False, raw=raw, reason=str(raw.get("reason") or "model declined to draft")
        )

    kind = raw.get("kind")
    if kind not in ("rule", "exemption"):
        return DraftResult(drafted=True, raw=raw, rejection=f"unknown draft kind {kind!r}")

    payload = raw.get(kind)
    if not isinstance(payload, dict):
        return DraftResult(drafted=True, raw=raw, rejection=f"missing {kind!r} object")

    # A human decides verification. Strip it rather than trusting a model that set it,
    # which is the one field where a confident model could do real damage.
    payload.pop("value_verified", None)
    payload.pop("verified_on", None)
    payload.setdefault("source", "DRAFT — pending human review")

    try:
        if kind == "rule":
            # Checked before model_validate so the message names the real problem: the
            # discriminated union would otherwise report a confusing per-variant error.
            cond_kind = (payload.get("condition") or {}).get("kind")
            if cond_kind not in CONDITION_KINDS:
                return DraftResult(
                    drafted=True,
                    raw=raw,
                    rejection=(
                        f"condition kind {cond_kind!r} is not in the closed vocabulary "
                        f"{sorted(CONDITION_KINDS)}"
                    ),
                )
            rule = Rule.model_validate(payload)
            return DraftResult(
                drafted=True, accepted=True, kind="rule", rule=rule, raw=raw,
                yaml=_to_yaml(payload, is_exemption=False),
            )

        exemption = Exemption.model_validate(payload)
        return DraftResult(
            drafted=True, accepted=True, kind="exemption", exemption=exemption, raw=raw,
            yaml=_to_yaml(payload, is_exemption=True),
        )
    except ValidationError as exc:
        return DraftResult(drafted=True, raw=raw, rejection=str(exc))


async def draft_rule(clause_text: str, hint: Optional[str] = None) -> DraftResult:
    """Propose one rule-pack entry from a passage of regulation.

    Raises LLMUnavailable if the provider cannot be reached; this is an authoring tool, so
    failing loudly is right. Unlike the explainer there is nothing to degrade to.
    """
    user = clause_text if not hint else f"{clause_text}\n\n---\nReviewer note: {hint}"

    resp: LLMResponse = await complete_json(
        system=DRAFTING_SYSTEM,
        user=user,
        temperature=0.0,  # translation, not composition
    )
    result = validate_draft(resp.data)
    result.usage = resp.usage

    if result.rejection:
        log.warning("rule draft rejected at the membrane: %s", result.rejection)
    return result
