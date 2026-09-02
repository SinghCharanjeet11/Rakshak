# Rakshak — Overview & Project Structure

**Rakshak** is a compliance-verification harness for autonomous payment-recovery agents. It ingests an agent's proposed action log and checks each action against a versioned rule-pack encoding the RBI Digital Payments E-mandate Framework 2026 (Circular RBI/DPSS/2026-27/396) and NPCI mandate rules, then returns a per-action pass/fail compliance report with the exact violated rule cited by clause.

Razorpay's Agent Studio ships agents that *act* (recovery, disputes, reconciliation). Rakshak verifies that such agents *acted legally*. It complements them; it does not compete.

Track fit: Track 02 (AI Risk Manager) — the official wording asks for a "detector, verifier, or auto-responder." Rakshak is a verifier. It is defense-only: it flags and reports, it never executes or blocks a payment.

---

## What it does, in one loop

1. A payment-recovery agent (real or simulated) produces a log of proposed actions — retry this mandate, send this nudge, debit this amount, escalate this case.
2. Rakshak ingests that log (clean JSON or messy free text).
3. For each action, a deterministic rule engine evaluates it against the encoded RBI/NPCI ruleset.
4. An LLM layer parses messy input into structured actions and writes a plain-English explanation + remediation for each violation.
5. Rakshak emits a compliance report: pass/fail per action, aggregate compliance score, every violation cited to its rule and source circular.

---

## Design principles (state these in the pitch)

- **The law is deterministic; only the fuzzy edges use AI.** Rule checks (retry counts, notice windows, thresholds) are hard-coded logic — an LLM must never "interpret" a legal threshold. AI is scoped to (a) parsing unstructured logs into structured actions, (b) generating human-readable violation explanations, (c) optionally proposing new adversarial test scenarios. This split is the honest answer to "is the AI decorative?"
- **Rules are a versioned artifact, not buried in code.** The rule-pack is a standalone, inspectable YAML file citing circular clauses. When RBI updates the rules, you bump the version — you don't rewrite the engine.
- **Every verdict is auditable.** A FAIL always names the rule id, the clause, the offending value, and the source circular. No black-box "looks non-compliant."
- **Human-in-the-loop only.** Rakshak produces reports for a human/agent to act on. It never auto-blocks a customer or files anything — that keeps it strictly defensive per Track 2 rules.

---

## Repository structure

```
rakshak/
├── README.md
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py                 # FastAPI entrypoint
│   │   ├── config.py               # settings, env loading
│   │   ├── api/
│   │   │   ├── routes_verify.py     # POST /verify, /verify/batch
│   │   │   ├── routes_reports.py    # GET /reports, /reports/{id}
│   │   │   ├── routes_rules.py      # GET /rules, /rules/versions
│   │   │   └── routes_health.py
│   │   ├── core/
│   │   │   ├── models.py            # Pydantic: Action, Violation, Report
│   │   │   ├── rule_engine.py       # deterministic evaluator (no LLM)
│   │   │   ├── rules_loader.py      # loads + validates rule-pack YAML
│   │   │   ├── scoring.py           # aggregate compliance score
│   │   │   └── run.py               # Run, Budget, RunStatus (harness model)
│   │   ├── orchestration/
│   │   │   ├── orchestrator.py      # bounded run loop, budget enforcement, fan-out
│   │   │   ├── membrane.py          # validate_membrane(): AI output -> typed Actions
│   │   │   └── eval_hooks.py        # non-blocking observability signals
│   │   ├── llm/
│   │   │   ├── ingestion_agent.py   # least-privilege subagent: free-text -> Actions
│   │   │   ├── explanation_agent.py # read-only subagent: violation -> prose
│   │   │   └── scenario_gen.py      # (optional) adversarial test generator
│   │   ├── rules/
│   │   │   ├── rbi_emandate_2026.yaml
│   │   │   └── npci_mandate.yaml
│   │   ├── store/
│   │   │   ├── db.py                # Postgres schema, pool, append-only trigger
│   │   │   └── repository.py        # runs, reports, append-only action_audit, raw_logs
│   │   └── seed/
│   │       ├── clean_actions.json
│   │       └── violating_actions.json
│   └── tests/
│       ├── test_rule_engine.py
│       ├── test_rules_loader.py
│       └── test_api.py
└── frontend/
    ├── package.json
    ├── next.config.js
    ├── tailwind.config.ts
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx                 # dashboard home
    │   ├── verify/page.tsx          # upload / paste log -> run
    │   ├── reports/[id]/page.tsx    # report detail
    │   └── rules/page.tsx           # rule-pack viewer
    ├── components/
    │   ├── UploadPanel.tsx
    │   ├── ComplianceScore.tsx
    │   ├── ActionTable.tsx
    │   ├── ViolationCard.tsx
    │   └── RulePackViewer.tsx
    └── lib/
        └── api.ts                   # typed fetch client
```

---

## The five documents in this spec

1. `00-overview.md` — this file: what, why, structure, principles.
2. `01-architecture.md` — **(v2, architecture-first)** the verification control plane: bounded non-recursive orchestration in Rakshak's own harness, the validation membrane, durable external state, least-privilege tools, cost budgets, and online eval hooks — wrapped around a deterministic core.
3. `02-system-design.md` — **(v2, architecture-first)** Part A: rule-pack schema + deterministic engine + encoded RBI/NPCI rules (the stable core). Part B: run/budget model, idempotency, durable-state SQL, eval-hook signals, orchestrator loop, membrane code. Part C/D: test strategy + demo seed data.
4. `03-backend.md` — FastAPI implementation: endpoints, modules, LLM integration, tests.
5. `04-frontend.md` — Next.js + Tailwind dashboard: pages, components, states, API client.
6. `05-requirements.md` — dependencies, env, setup, run, seed data, 14-day build plan, MVP scope, demo script.

---

## MVP boundary (what "done" means for the buildathon)

MUST: rule engine with 5–6 encoded rules; ingest a batch of ≥20 actions (clean + planted violations); pass/fail report with per-violation clause citation; one real Razorpay test-mode webhook sequence run through it; a dashboard that shows the score and the violation drill-down.

SHOULD: LLM free-text parser; plain-English remediation; versioned rule-pack file.

NICE: adaptive LLM scenario generator; compliance-score trend across batches.

OUT OF SCOPE: any action execution; a voice pipeline; a generic hallucination/PII guardrail.
