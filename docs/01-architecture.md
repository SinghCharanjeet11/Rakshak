# Rakshak — System Architecture (v2, architecture-first)

> This revision is written for a panel that judges **architecture above all** and that built Razorpay Agent Studio on Anthropic's Claude Agent SDK. It speaks the production-agent vocabulary that panel uses — durable state, bounded orchestration, least-privilege tools, cost caps, and online evaluation hooks — while preserving Rakshak's core thesis: **a hard wall between AI reasoning and the deterministic verdict.** The two ideas are not in tension; the sophistication is in how cleanly they're separated.
>
> **OPEN-1 was resolved on 2026-09-02: Rakshak does not use the Claude Agent SDK, and that is a decision rather than an omission.** The model layer makes exactly one stateless, schema-constrained JSON call with zero tools declared to the provider. An agent-loop harness — the Agent SDK, the API tool runner, or any equivalent — would be machinery wrapped around a single completion. Adopting one to match a slide would contradict the thesis this document opens with. The provider is OpenAI `gpt-4o-mini`, reached through `llm/_provider.py`; every constraint named below is enforced by Rakshak's own orchestrator, in code you can read, not inherited from a vendor harness.

---

## 1. The one architectural idea to defend

Rakshak is a **verification control plane** built as a *bounded multi-agent pipeline in front of a deterministic decision core.* Everything an LLM does is untrusted, budgeted, sandboxed, and re-validated before it can touch a verdict. The verdict itself is produced by pure, versioned, auditable code that no model can influence.

Say it in one line in the interview: *"AI on the outside for messy reality, deterministic law on the inside for the verdict, and a validation membrane between them that every AI output must cross."*

This is the same shape Agent Studio needs but inverted in purpose — Studio's agents *act*; Rakshak's agents *judge whether an action was legal*, and unlike an acting agent, a judging system cannot be allowed to hallucinate its judgment. That constraint is what makes the architecture interesting.

---

## 2. Layered view

```
┌──────────────────────────────────────────────────────────────────────┐
│  CLIENT — Next.js dashboard (typed, read-only over the API)           │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │ HTTPS / JSON
┌───────────────────────────────▼──────────────────────────────────────┐
│  EDGE / API — FastAPI gateway                                         │
│  · request validation · idempotency keys · rate + cost budget check   │
│  · auth (API key / tenant) · correlation-id issuance                  │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │
┌───────────────────────────────▼──────────────────────────────────────┐
│  ORCHESTRATION LAYER — bounded, non-recursive (own orchestrator)      │
│                                                                        │
│   ┌─────────────────────────── Orchestrator ─────────────────────┐    │
│   │  plans the run · enforces per-run turn + token + ₹ budget     │    │
│   │  · fans out to flat specialist subagents · aggregates         │    │
│   └───────┬───────────────────┬───────────────────┬──────────────┘    │
│           │ (parallel, 1 level deep — no sub-subagents)               │
│   ┌───────▼──────┐   ┌────────▼────────┐   ┌───────▼────────┐          │
│   │ Ingestion    │   │ (verdict is NOT │   │ Explanation    │          │
│   │ Subagent     │   │  an agent — it's │   │ Subagent       │          │
│   │ text→Actions │   │  the core below) │   │ violation→prose│          │
│   └───────┬──────┘   └─────────────────┘   └───────┬────────┘          │
│           │                                        │                   │
│   ══════ VALIDATION MEMBRANE (Pydantic re-validation, schema gate) ══  │
└───────────┼────────────────────────────────────────┼──────────────────┘
            │ structured Actions                      │ prose (read-only)
┌───────────▼────────────────────────────────────────▼──────────────────┐
│  DETERMINISTIC DECISION CORE  (no LLM, no network, pure functions)     │
│  · RuleEngine.evaluate(actions, pack) → Violations                     │
│  · Scoring.compute() → score      · Exemption resolver                 │
│  ← loads ← Rule-pack (versioned YAML artifact, cites RBI/NPCI clauses)  │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │ Report
┌───────────────────────────────▼──────────────────────────────────────┐
│  STATE + OBSERVABILITY (state lives OUTSIDE the process)              │
│  · Postgres: reports, runs, action-audit   · object store: raw logs   │
│  · Eval hooks: tool-call validity, injection heuristics, trajectory   │
│  · Metrics: per-run cost, latency, membrane-rejection rate            │
└──────────────────────────────────────────────────────────────────────┘
```

Five layers, one membrane. The membrane is the star.

---

## 3. Why a bounded multi-agent design and not one prompt

An honest architect must justify multi-agent, because the naive answer ("more agents = more impressive") is wrong and a good panel will punish it. The justification here is **separation of trust and concern**, not parallelism for its own sake:

- **Ingestion** and **Explanation** are genuinely different jobs with different prompts, different failure modes, and different trust levels (ingestion output is untrusted structured data that gates into the core; explanation output is untrusted prose that never gates into anything). Giving each its own bounded subagent means each can be evaluated, budgeted, and permissioned independently.
- They run **in parallel where independent** (multiple logs, or ingestion of batch N while explanation of batch N-1 renders), so wall-clock latency is bounded by the slowest branch, not the sum. This is the fan-out/gather pattern.
- Critically, **the verdict is deliberately NOT an agent.** The most defensible decision in the whole design is choosing *not* to make the thing that matters agentic. State that out loud — it signals you know when not to use AI.

### Agent-harness constraints honored (say these unprompted)

These are the constraints a production agent harness imposes. Rakshak honours them in its own orchestrator rather than inheriting them from one — which means they are enforced in code that ships in this repo and is covered by tests, not delegated to a dependency.

- **Subagents are one level deep — no recursive delegation.** The orchestrator fans out to flat specialists; no subagent spawns another. `orchestrator.py` contains no recursion, and `test_least_privilege.py` pins the tool surface of each.
- **Bounded turns.** Each subagent runs under an explicit turn ceiling (25 by default, matching common harness defaults); the orchestrator caps total run turns rather than letting a subtask loop.
- **Budgets are product features, not billing alerts.** Per-run and per-tenant caps on tokens and ₹-cost live in the orchestrator harness; a run that would exceed its cap is halted and reported, not silently continued.

---

## 4. The validation membrane (the defensible centerpiece)

Every byte an LLM produces crosses one gate before it can affect anything:

1. **Ingestion output** → parsed JSON → `Action.model_validate()` per item. A hallucinated field, an invented amount, or a malformed timestamp fails validation and is dropped/flagged — it can never reach `evaluate()` as a fact. The LLM can misread a log; it cannot fabricate a compliant-looking action that the engine then blesses, because the engine only sees schema-valid structured data and applies law to it regardless of how it was parsed.
2. **Explanation output** → treated as display text only, attached to an *already-decided* `Violation`. It is never parsed back into a verdict, so a persuasive-but-wrong explanation cannot flip a pass/fail.

The membrane is why "the AI could be wrong" is not a threat to correctness — the worst an AI error does is produce a malformed action (rejected) or a poor sentence (cosmetic). The verdict is structurally isolated from model error. This is the answer that wins the "how do I trust an AI compliance tool?" question.

---

## 5. Component responsibilities (delta from v1)

**API gateway** — now also issues a **correlation id** per run, enforces an **idempotency key** (same log + same rule version ⇒ same report, no duplicate work), and checks the **cost budget** before dispatching to the orchestrator.

**Orchestrator** — new component. Plans the run, enforces turn/token/₹ budgets, fans out to subagents, aggregates, and writes the run record. Contains no compliance logic — it moves work, it doesn't judge.

**Ingestion subagent** — the former parser, now a budgeted, least-privilege agent whose only tool is "read the provided log." No network, no other tools — least-privilege scoping so a prompt-injection payload inside a log can't reach anything.

**Explanation subagent** — the former explainer, batched, read-only over verdicts.

**Deterministic decision core** — unchanged and deliberately so: `evaluate`, `scoring`, exemptions, rule-pack loader. Pure, tested, versioned. The stable heart.

**State + observability** — new, and load-bearing for the "production architecture" story (below).

---

## 6. State lives outside the process

A demo keeps state in memory; a production architecture does not. Rakshak treats the request as ephemeral and **durable storage as the source of truth**:

- **Postgres** — `runs` (id, tenant, rulepack_version, budget, cost, status, timings), `reports`, and an append-only `action_audit` (every action + its verdict + the clause). Append-only audit is itself a compliance-grade property — you can prove what was checked and when.
- **Object store** (or a blob column for MVP) — the raw submitted logs, referenced by the run, so a report is always reproducible from its inputs.
- **Resumption is free once state is durable** — a run that's interrupted can be re-derived because inputs + rule version + engine determinism fully determine the output. Re-running a stored run against a *newer* rule-pack is a feature: "re-verify last month's agent behavior under the April 2026 rules."

This directly echoes the production-agent guidance the panel follows: durable state, not in-process session.

---

## 7. Online evaluation hooks (the detail that reads as senior)

After each subagent turn, non-blocking hooks write signals to the observability pipeline (they never add latency to the user response):

- **Tool-call validity** — did the ingestion subagent stay within its single permitted tool with valid arguments?
- **Injection heuristics** — does a submitted log contain instruction-like text matching known prompt-injection patterns? (Relevant because Rakshak *ingests logs that may themselves be adversarial* — a nice reflexive touch: the verifier watches its own inputs.)
- **Membrane-rejection rate** — how often did LLM output fail re-validation? A rising rate flags a parser regression or a new log format.
- **Trajectory / cost per run** — tokens and ₹ per verification, tracked per tenant against the cap.

These make Rakshak legible in production, and naming them tells the panel you know agents "fail slowly, expensively, and in ways that evade local testing."

---

## 8. Request lifecycle (v2)

```
1. POST /verify/batch  { format, payload, rulepack_version?, idempotency_key? }
2. Gateway: validate envelope · auth/tenant · budget check · issue correlation_id
3. Idempotency: if key seen → return stored report (no recompute)
4. Orchestrator: open run record (status=running, budget set)
5. If text →  Ingestion subagent (budgeted, 1 tool) → JSON
   If json →  skip
6. ══ MEMBRANE ══  Action.model_validate(...)  → structured actions (or reject)
7. CORE:  violations = RuleEngine.evaluate(actions, pack)     [deterministic]
8. CORE:  score = Scoring.compute(actions, violations)        [deterministic]
9. Explanation subagent (batched, read-only) → prose per violation
10. Persist: report + append action_audit + close run (status=done, cost, timings)
11. Eval hooks fire async (non-blocking)
12. Return Report (+ correlation_id)
```

Steps 7–8 — the only steps that decide compliance — sit *after* the membrane and contain no AI. Everything sophisticated (agents, budgets, hooks) surrounds a boring, correct, deterministic center. That contrast is the architecture's whole aesthetic.

---

## 9. What each architectural choice answers in the interview

| Panel question | The choice that answers it |
|---|---|
| "Can your AI hallucinate a compliance verdict?" | The validation membrane + non-agentic core |
| "Why multi-agent — isn't one prompt enough?" | Separation of trust/concern; parallel fan-out; independent budgeting |
| "You built on our SDK — did you respect its limits?" | One-level subagents, bounded turns, no recursion |
| "What happens under load / on failure?" | Durable external state, idempotency, resumable runs, cost caps |
| "How do you know it's behaving in production?" | Online eval hooks: tool validity, injection heuristics, membrane-rejection rate |
| "Isn't ingesting agent logs a security risk?" | Least-privilege ingestion tool + injection heuristics on inputs |
| "Why didn't you just use Agent Studio?" | Studio agents act; Rakshak is the verification control plane above them |

---

## 10. Deliberate non-goals (naming these is itself senior)

- **No recursive agent hierarchy** — the SDK forbids it and the problem doesn't need it. Depth here would be architecture-theater.
- **No LLM in the verdict path** — non-negotiable; it's the thesis.
- **No streaming token UI** — irrelevant to a batch verifier; would be complexity for show.
- **No live money movement** — defense-only, report-only (Track 2 requirement).

The strongest architectural signal you can send this panel is knowing exactly where *not* to add sophistication.
