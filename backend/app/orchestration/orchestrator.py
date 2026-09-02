"""Bounded, non-recursive orchestration — 02-system-design.md §B.6, 01-architecture.md §8.

Plans the run, enforces turn/token/rupee budgets, fans out to flat specialist subagents,
calls the deterministic core between them, persists, and closes the run.

**Contains no compliance logic.** It moves work; it does not judge. Every PASS/FAIL in the
report below was decided by `core/`, and the orchestrator cannot influence one.

Two SDK boundaries are honored deliberately and worth stating out loud:

* **Subagents are one level deep.** The orchestrator fans out to flat specialists;
  no subagent spawns another. There is no recursion anywhere in this file.
* **Budgets halt, they do not warn.** A run that would exceed a cap ends
  `HALTED_BUDGET` with a *partial report*, never a silent overrun.

The pipeline's shape is the whole architectural argument: everything sophisticated —
agents, budgets, hooks — surrounds steps 4 and 5, which are boring, pure and correct.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel

from app.adapters.razorpay import RazorpayAdapterError, map_webhook_payload
from app.config import settings
from app.core.models import Action, Report
from app.core.rule_engine import evaluate_detailed
from app.core.rules_loader import RulePack, RulePackError, load_pack
from app.core.run import Budget, BudgetExceeded, Run, RunStatus
from app.core.scoring import compute, summarize
from app.llm import explanation_agent, ingestion_agent
from app.llm._provider import LLMUnavailable, Usage
from app.orchestration.eval_hooks import emit_eval, scan_for_injection
from app.orchestration.membrane import MembraneError, validate_membrane_detailed
from app.store import repository

log = logging.getLogger("rakshak.orchestrator")

_PACK_CACHE: dict[str, RulePack] = {}


class VerifyRequest(BaseModel):
    format: Literal["json", "text", "razorpay"] = "json"
    payload: Any
    rulepack_version: Optional[str] = None
    idempotency_key: Optional[str] = None
    tenant_id: str = "default"


class RunOutcome(BaseModel):
    report: Report
    run: Run
    reused: bool = False  # served from the idempotency cache, no recompute


def get_pack(version: Optional[str] = None) -> RulePack:
    key = version or settings.ACTIVE_RULEPACK
    if key not in _PACK_CACHE:
        _PACK_CACHE[key] = load_pack(key)
    return _PACK_CACHE[key]


def clear_pack_cache() -> None:
    _PACK_CACHE.clear()


def derive_idempotency_key(payload: Any, rulepack_version: str) -> str:
    """sha256(canonical_json(payload) + rulepack_version) — 02-system-design.md §B.3.

    Same input plus same rule version must yield the same key, so `sort_keys` and a
    stable separator matter: they are what make the determinism claim *observable*
    rather than merely asserted."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((canonical + rulepack_version).encode("utf-8")).hexdigest()


def _guard_budget(run: Run, *, turns: int = 0, tokens: int = 0, cost_inr: float = 0.0) -> None:
    """Pre-turn cap check. Called *before* spending, so a cap is never crossed."""
    if run.turns_used + turns > run.budget.max_total_turns:
        raise BudgetExceeded("max_total_turns", run.budget.max_total_turns, run.turns_used + turns)
    if run.tokens_used + tokens > run.budget.max_tokens:
        raise BudgetExceeded("max_tokens", run.budget.max_tokens, run.tokens_used + tokens)
    if run.cost_inr + cost_inr > run.budget.max_cost_inr:
        raise BudgetExceeded("max_cost_inr", run.budget.max_cost_inr, run.cost_inr + cost_inr)


def _account(run: Run, usage: Usage, turn_label: str) -> None:
    """Post-turn accounting, then a *post-hoc* cap check so an overrun still halts."""
    run.turns_used += 1
    run.tokens_used += usage.total_tokens
    run.cost_inr = round(run.cost_inr + usage.cost_inr, 6)
    emit_eval(
        run.id, "trajectory_cost", float(usage.total_tokens),
        turn=run.turns_used, stage=turn_label, cost_inr=usage.cost_inr,
    )
    _guard_budget(run)


def _assemble(
    run: Run,
    actions: list[Action],
    violations: list,
    exemptions_applied: list,
    partial: bool = False,
) -> Report:
    result = compute(actions, violations, mode=settings.SCORING_MODE)
    summary = summarize(result, violations)
    if partial:
        summary = f"PARTIAL — run halted on budget. {summary}"
    return Report(
        id=f"rep_{uuid.uuid4().hex[:20]}",
        created_at=datetime.now(timezone.utc),
        rulepack_version=run.rulepack_version,
        actions=actions,
        violations=violations,
        exemptions_applied=exemptions_applied,
        score=result.score,
        passed=result.passed,
        failed=result.failed,
        summary=summary,
        correlation_id=run.correlation_id,
        run_id=run.id,
    )


async def run_verification(req: VerifyRequest) -> RunOutcome:
    """The bounded run loop. Steps mirror 01-architecture.md §8 one-to-one."""

    # 1-2. resolve the rule-pack and open the run record
    try:
        pack = get_pack(req.rulepack_version)
    except RulePackError as exc:
        raise ValueError(str(exc)) from exc

    idem = req.idempotency_key or derive_idempotency_key(req.payload, pack.version)

    # 3. idempotency: a terminal run with this key is served from storage, no recompute
    # Scoped to the tenant: an unscoped lookup would let one tenant's key collide with
    # another's stored run and return that tenant's whole report.
    existing = repository.find_run_by_idempotency_key(idem, tenant_id=req.tenant_id)
    if existing is not None:
        if existing.status in (RunStatus.DONE, RunStatus.HALTED_BUDGET):
            if (stored := repository.get_report_for_run(existing.id)) is not None:
                log.info("idempotent hit run=%s key=%s", existing.id, idem[:12])
                return RunOutcome(report=stored, run=existing, reused=True)
        idem = None  # a failed/in-flight run must not block a fresh attempt

    run = Run(
        id=f"run_{uuid.uuid4().hex[:20]}",
        tenant_id=req.tenant_id,
        correlation_id=f"cor_{uuid.uuid4().hex[:16]}",
        rulepack_version=pack.version,
        idempotency_key=idem,
        status=RunStatus.RUNNING,
        budget=Budget(
            max_turns=settings.BUDGET_MAX_TURNS,
            max_total_turns=settings.BUDGET_MAX_TOTAL_TURNS,
            max_tokens=settings.BUDGET_MAX_TOKENS,
            max_cost_inr=settings.BUDGET_MAX_COST_INR,
            max_actions=settings.BUDGET_MAX_ACTIONS,
        ),
        started_at=datetime.now(timezone.utc),
    )
    repository.open_run(run)
    repository.save_raw_log(run.id, req.format, req.payload)

    actions: list[Action] = []
    violations: list = []
    exemptions_applied: list = []

    try:
        # 4-5. ingestion (only for free text) then the membrane
        if req.format == "text":
            raw_text = req.payload if isinstance(req.payload, str) else str(req.payload)

            # Reflexive check: the verifier watches its own inputs (OWASP LLM01).
            scan = scan_for_injection(raw_text)
            emit_eval(
                run.id, "injection_heuristic", scan.score,
                turn=run.turns_used, matched=scan.matched, excerpts=scan.excerpts,
            )

            _guard_budget(run, turns=1)
            resp = await ingestion_agent.parse(raw_text)  # LLMUnavailable -> outer handler
            _account(run, resp.usage, "ingestion")

            # Least-privilege assertion at runtime, not just in tests: the ingestion
            # agent is given no tools, so any tool call at all is out of contract.
            emit_eval(
                run.id, "tool_call_validity", 0.0 if resp.tool_calls else 1.0,
                turn=run.turns_used, called=resp.tool_calls,
            )

            membrane = validate_membrane_detailed(
                resp.data, run.id, turn=run.turns_used, max_actions=run.budget.max_actions
            )
            emit_eval(
                run.id, "parse_coverage",
                ingestion_agent.parse_coverage(raw_text, len(membrane.actions)),
                turn=run.turns_used,
            )
        elif req.format == "razorpay":
            # A pure, deterministic rename-and-convert. No model involved, and the result
            # still crosses the membrane — a mapping bug yields a rejected action, never
            # a bad verdict.
            try:
                mapped = map_webhook_payload(req.payload)
            except RazorpayAdapterError as exc:
                raise MembraneError(str(exc)) from exc
            membrane = validate_membrane_detailed(
                mapped, run.id, turn=run.turns_used, max_actions=run.budget.max_actions
            )
        else:
            membrane = validate_membrane_detailed(
                req.payload, run.id, turn=run.turns_used, max_actions=run.budget.max_actions
            )

        actions = membrane.actions

        # 6-7. THE CORE. Deterministic, no LLM, no network. The only steps that decide.
        evaluation = evaluate_detailed(actions, pack)
        violations = evaluation.violations
        exemptions_applied = evaluation.exemptions_applied

        # 8. explanation subagent — read-only over already-decided verdicts, batched.
        #    Budget-skipped rather than budget-failed: prose is never worth halting for.
        if violations and settings.llm_enabled:
            try:
                _guard_budget(run, turns=1)
                explanations, usage = await explanation_agent.explain_batch(violations)
                _account(run, usage, "explanation")
                explanation_agent.attach(violations, explanations)
            except BudgetExceeded as exc:
                log.info("skipping explanations, budget: %s", exc)

        # 9. persist + close
        report = _assemble(run, actions, violations, exemptions_applied)
        repository.save_report(report, run.id)
        repository.append_audit(run.id, actions, violations)
        repository.close_run(run, RunStatus.DONE)
        return RunOutcome(report=report, run=run)

    except BudgetExceeded as exc:
        log.warning("run=%s halted on budget: %s", run.id, exc)
        report = _assemble(run, actions, violations, exemptions_applied, partial=True)
        repository.save_report(report, run.id)
        if actions:
            repository.append_audit(run.id, actions, violations)
        repository.close_run(run, RunStatus.HALTED_BUDGET)
        return RunOutcome(report=report, run=run)

    except (MembraneError, LLMUnavailable):
        repository.close_run(run, RunStatus.FAILED)
        raise

    except Exception:
        log.exception("run=%s failed", run.id)
        repository.close_run(run, RunStatus.FAILED)
        raise


async def replay(run_id: str, rulepack_version: Optional[str] = None) -> RunOutcome:
    """Re-verify a stored run's raw log under a chosen rule-pack version.

    Free once state is durable: inputs + rule version + engine determinism fully determine
    the output. "Re-verify last month's agent behaviour under the April 2026 rules" is a
    first-class feature, not a migration (01-architecture.md §6).

    The idempotency key is derived normally rather than bypassed, which makes replay do
    the more interesting thing in both directions: replaying under the *same* pack returns
    the identical stored report with no recompute (determinism, demonstrated), while
    replaying under a *different* pack changes the key and genuinely re-verifies.
    """
    stored = repository.get_raw_log(run_id)
    if stored is None:
        raise KeyError(f"no stored log for run {run_id}")

    payload: Any = stored["content"]
    if stored["format"] in ("json", "razorpay"):
        payload = json.loads(payload)

    return await run_verification(
        VerifyRequest(
            format=stored["format"],  # type: ignore[arg-type]
            payload=payload,
            rulepack_version=rulepack_version,
        )
    )
