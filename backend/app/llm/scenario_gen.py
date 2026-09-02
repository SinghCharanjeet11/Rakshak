"""Adversarial scenario generator (optional — NICE tier in 00-overview.md).

Given the rule-pack, emit synthetic Action batches likely to violate under-tested rules.
Same json_object + re-validation pattern as ingestion, and **never part of the verdict
path**: generated actions are inputs to be judged, exactly like any submitted log.

First on the cut list if time slips (05-requirements.md §7).
"""

from __future__ import annotations

import json

from app.core.rules_loader import RulePack
from app.llm._provider import LLMResponse, complete_json

SCENARIO_SYSTEM = """\
You generate synthetic test data for a payment-compliance verifier. Given a list of rules, \
produce action records designed to probe them — some clearly violating, some clearly \
compliant, and some sitting exactly on a boundary (one rupee under a threshold, one minute \
short of a notice window).

Return {"actions": [...]} using the same Action schema the ingestion agent uses. Every item \
needs at least id, type and timestamp. Do not label which ones you think violate — the \
engine decides that, not you.\
"""


async def generate(pack: RulePack, count: int = 10) -> LLMResponse:
    rules = [
        {
            "id": r.id,
            "title": r.title,
            "applies_to": [t.value for t in r.applies_to],
            "condition": r.condition.model_dump(),
        }
        for r in pack.rules
    ]
    user = json.dumps({"count": count, "rules": rules}, ensure_ascii=False)
    return await complete_json(system=SCENARIO_SYSTEM, user=user, temperature=0.8)
