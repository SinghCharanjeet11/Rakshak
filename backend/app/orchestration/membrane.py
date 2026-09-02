"""The validation membrane — 02-system-design.md §B.7, 01-architecture.md §4.

**The defensible centerpiece.** Every byte an LLM produces crosses this gate before it
can affect anything. Nothing that fails validation reaches `evaluate()`; the verdict path
sees only well-typed facts, applied against versioned law, by pure code.

This is why "the AI could be wrong" is not a threat to correctness. The worst an ingestion
error can do is produce a malformed action (rejected and counted here) or omit one. It
cannot fabricate a compliant-looking action that the engine then blesses, because the
engine applies the law to whatever it is given regardless of how it was parsed.

Note the asymmetry that makes the guarantee hold: rejection is *conservative*. A rejected
item is reported as a rejection, never silently treated as a pass.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from app.core.models import Action
from app.orchestration.eval_hooks import emit_eval

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.M)


class MembraneRejection(BaseModel):
    index: int
    reason: str
    raw_excerpt: str


class MembraneResult(BaseModel):
    actions: list[Action] = Field(default_factory=list)
    rejections: list[MembraneRejection] = Field(default_factory=list)
    total_items: int = 0

    @property
    def rejection_rate(self) -> float:
        return len(self.rejections) / max(self.total_items, 1)


class MembraneError(Exception):
    """The payload was not a list of action-shaped objects at all."""


def _strip_fences(text: str) -> str:
    return _FENCE.sub("", text).strip()


def _coerce_items(raw: Any) -> list[Any]:
    """Accept a list, a {"actions": [...]} envelope, or a JSON string of either."""
    if isinstance(raw, str):
        try:
            raw = json.loads(_strip_fences(raw))
        except json.JSONDecodeError as exc:
            raise MembraneError(f"payload is not valid JSON: {exc}") from exc

    if isinstance(raw, dict):
        for key in ("actions", "items", "data"):
            if isinstance(raw.get(key), list):
                return raw[key]
        raise MembraneError(
            "JSON object payload must carry an 'actions' array"
        )

    if isinstance(raw, list):
        return raw

    raise MembraneError(f"payload must be a list or an object with 'actions', got {type(raw).__name__}")


def validate_membrane_detailed(
    raw: Any,
    run_id: str,
    turn: int = 0,
    max_actions: Optional[int] = None,
) -> MembraneResult:
    items = _coerce_items(raw)

    if max_actions is not None and len(items) > max_actions:
        raise MembraneError(
            f"payload carries {len(items)} actions, above the run budget cap of {max_actions}"
        )

    result = MembraneResult(total_items=len(items))
    for i, item in enumerate(items):
        try:
            result.actions.append(Action.model_validate(item))
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {}
            field = ".".join(str(p) for p in first.get("loc", ())) or "?"
            result.rejections.append(
                MembraneRejection(
                    index=i,
                    reason=f"{field}: {first.get('msg', 'invalid')}",
                    raw_excerpt=str(item)[:200],
                )
            )

    emit_eval(
        run_id,
        "membrane_rejection",
        result.rejection_rate,
        turn=turn,
        rejected=len(result.rejections),
        total=result.total_items,
    )
    return result


def validate_membrane(raw: Any, run_id: str, turn: int = 0) -> list[Action]:
    """The contract quoted in 02-system-design.md §B.7."""
    return validate_membrane_detailed(raw, run_id, turn).actions
