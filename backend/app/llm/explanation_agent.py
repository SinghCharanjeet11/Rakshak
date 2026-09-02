"""Explanation subagent — decided Violation -> prose + remediation.

Read-only over verdicts, **zero tools**, batched into a single call. It receives the rule
title, clause and offending value for violations the deterministic engine has *already*
decided, and is forbidden from second-guessing them.

Its output is display text (invariant I8). It is attached to an already-decided
`Violation` and never parsed back into anything, so a persuasive-but-wrong explanation is
cosmetic — it cannot flip a pass/fail. This is why the failure mode here is "no prose",
not "wrong verdict", and why the caller degrades gracefully instead of erroring.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.models import Violation
from app.llm._provider import LLMResponse, LLMUnavailable, Usage, complete_json

log = logging.getLogger("rakshak.llm.explain")

# Zero tools. Asserted by tests/test_least_privilege.py.
EXPLANATION_TOOLS: list[dict[str, Any]] = []

EXPLANATION_SYSTEM = """\
You are given a list of compliance violations that have ALREADY been decided by a \
deterministic rule engine. Your job is to explain them to a compliance officer.

For each violation write a 2-3 sentence plain-English explanation and one concrete \
remediation. Name the specific offending value. Keep it factual and unhedged.

Do NOT question whether it is a violation. Do NOT change or comment on the severity. Do NOT \
suggest the engine may be wrong. The verdict is settled; you are writing the caption.

Return a JSON object of the form:
  {"explanations": [{"action_id": "...", "text": "..."}, ...]}
in the same order as the input, one entry per input violation.\
"""


async def explain_batch(violations: list[Violation]) -> tuple[dict[str, str], Usage]:
    """Returns {action_id: prose}. Never raises — an explainer failure must not block a
    report (invariant I9)."""
    if not violations:
        return {}, Usage()

    payload = [
        v.model_dump(include={"action_id", "rule_id", "title", "clause", "offending_value"})
        for v in violations
    ]

    try:
        resp: LLMResponse = await complete_json(
            system=EXPLANATION_SYSTEM,
            user=json.dumps(payload, ensure_ascii=False),
            temperature=0.3,
        )
    except LLMUnavailable as exc:
        log.warning("explanation unavailable, returning verdicts without prose: %s", exc)
        return {}, Usage()

    out: dict[str, str] = {}
    for e in resp.data.get("explanations", []):
        # Only the two display fields are read. Nothing here can touch a verdict field
        # even if the model volunteers one.
        if isinstance(e, dict) and isinstance(e.get("action_id"), str) and isinstance(e.get("text"), str):
            out[e["action_id"]] = e["text"]

    return out, resp.usage


def attach(violations: list[Violation], explanations: dict[str, str]) -> list[Violation]:
    """Attach prose to already-decided violations, leaving every verdict field alone."""
    for v in violations:
        if (text := explanations.get(v.action_id)) is not None:
            v.explanation = text
    return violations
