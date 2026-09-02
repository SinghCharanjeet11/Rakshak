"""Online evaluation hooks — 02-system-design.md §B.5, 01-architecture.md §7.

Non-blocking observability. These signals are written after each turn and are *never* on
the response's critical path: emitting is an in-memory append plus a log line, and the
sink is swappable for a real metrics pipeline without touching a caller.

Emitted kinds:
    tool_call_validity   1.0 if the subagent used only its permitted tool, else 0.0
    injection_heuristic  score that the submitted log contains instruction-like text
    membrane_rejection   fraction of LLM-emitted items that failed Action re-validation
    trajectory_cost      tokens + INR spent this turn
    parse_coverage       fraction of log lines mapped to structured actions

`injection_heuristic` is the reflexive one: Rakshak ingests logs that may themselves be
adversarial, so the verifier watches its own inputs for OWASP LLM01.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict, deque
from typing import Any, Deque, Optional

from pydantic import BaseModel, Field

log = logging.getLogger("rakshak.eval")

MAX_SIGNALS_PER_RUN = 200


class EvalSignal(BaseModel):
    run_id: str
    turn: int
    kind: str
    value: float
    meta: dict[str, Any] = Field(default_factory=dict)


class InMemorySink:
    """MVP sink. Bounded per run so a pathological run cannot exhaust memory."""

    def __init__(self) -> None:
        self._signals: dict[str, Deque[EvalSignal]] = defaultdict(
            lambda: deque(maxlen=MAX_SIGNALS_PER_RUN)
        )

    def write(self, signal: EvalSignal) -> None:
        self._signals[signal.run_id].append(signal)
        log.info(
            "eval run=%s turn=%s %s=%.4f %s",
            signal.run_id, signal.turn, signal.kind, signal.value, signal.meta or "",
        )

    def for_run(self, run_id: str) -> list[EvalSignal]:
        return list(self._signals.get(run_id, ()))

    def clear(self) -> None:
        self._signals.clear()


SINK = InMemorySink()


def emit_eval(
    run_id: str,
    kind: str,
    value: float,
    turn: int = 0,
    **meta: Any,
) -> None:
    """Fire-and-forget. Must never raise into the caller — a broken metric is not an
    outage, and an observability failure must not fail a verification."""
    try:
        SINK.write(EvalSignal(run_id=run_id, turn=turn, kind=kind, value=value, meta=meta))
    except Exception:  # pragma: no cover - defensive
        log.exception("eval hook failed (suppressed)")


def signals_for(run_id: str) -> list[EvalSignal]:
    return SINK.for_run(run_id)


# --------------------------------------------------------------------------
# injection heuristic (OWASP LLM01)
# --------------------------------------------------------------------------

INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("override_instructions", re.compile(r"\bignore\s+(all\s+)?(prior|previous|above|earlier)\b", re.I)),
    ("disregard_instructions", re.compile(r"\bdisregard\s+(all\s+)?(prior|previous|the\s+above)\b", re.I)),
    ("forget_instructions", re.compile(r"\bforget\s+(everything|all|your)\b", re.I)),
    ("verdict_steering", re.compile(r"\bmark\s+(every|all|each)\b[^.\n]{0,40}\bcompliant\b", re.I)),
    ("verdict_steering", re.compile(r"\b(set|report)\s+all\s+violations?\s+to\s+(none|zero|empty)\b", re.I)),
    ("suppress_output", re.compile(r"\breturn\s+an?\s+empty\s+(actions?\s+)?(array|list|object)\b", re.I)),
    ("suppress_output", re.compile(r"\bdo\s+not\s+report\b", re.I)),
    ("role_hijack", re.compile(r"\byou\s+are\s+now\b|\bnew\s+(system\s+)?instructions?\b", re.I)),
    ("fake_system_frame", re.compile(r"#{2,}\s*(system|instruction)", re.I)),
    ("fake_system_frame", re.compile(r"\b(system\s+note|system\s+prompt)\b[^.\n]{0,30}\bparser\b", re.I)),
    ("authority_claim", re.compile(r"\bregulatory\s+waiver\b|\bexempt\s+from\s+all\b", re.I)),
]


class InjectionScan(BaseModel):
    score: float  # 0.0 (clean) .. 1.0
    matched: list[str] = Field(default_factory=list)
    excerpts: list[str] = Field(default_factory=list)

    @property
    def suspicious(self) -> bool:
        return self.score > 0.0


def scan_for_injection(text: str) -> InjectionScan:
    """Heuristic, not a filter.

    Nothing here blocks a run — the architecture does not need it to. The membrane and
    the non-agentic core already make a successful injection unable to change a verdict;
    this signal exists so an operator can *see* that someone tried.
    """
    if not text:
        return InjectionScan(score=0.0)

    matched: list[str] = []
    excerpts: list[str] = []
    distinct_categories: set[str] = set()

    for name, pattern in INJECTION_PATTERNS:
        m = pattern.search(text)
        if m:
            distinct_categories.add(name)
            matched.append(name)
            line = text[max(0, m.start() - 40) : m.end() + 40].replace("\n", " ").strip()
            excerpts.append(line)

    # Score by distinct categories tripped, not raw hits: a log that repeats one phrase
    # is one attempt, while a log tripping four different categories is a real payload.
    denominator = len({name for name, _ in INJECTION_PATTERNS})
    score = min(1.0, len(distinct_categories) / max(denominator / 2, 1))

    return InjectionScan(
        score=round(score, 4),
        matched=sorted(distinct_categories),
        excerpts=excerpts[:5],
    )
