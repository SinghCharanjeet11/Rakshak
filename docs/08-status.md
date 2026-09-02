# Rakshak — status

> What is built, what is verified, and what is left. Audited against `00-overview.md`
> (MVP boundary) and `05-requirements.md` (§5 FRs, §6 NFRs, §7 plan, §8 deliverables).
>
> Last audited: 2026-08-24 · **Nothing is committed to git yet.**

---

## At a glance

| | |
|---|---|
| Backend tests | **190 passing** (on Postgres) |
| Browser E2E tests | **23 passing** (Playwright, against the real stack) |
| Typecheck / build | clean |
| Source | 29 Python modules, 24 React components/routes |
| Single-action verdict | **7.9µs p50 / 13.8µs p99** (`scripts/bench_verify.py`) |
| Blocked on you | 4 items — see [What I need from you](#what-i-need-from-you) |

**One-line summary:** every MVP **MUST** is now met, including real Razorpay data. What
remains is the regulatory verification (OPEN-2), one live model run, and the push.

---

## MVP boundary (`00-overview.md`)

### MUST

| Requirement | Status |
|---|---|
| Rule engine with 5–6 encoded rules | ✅ 6 rules + 1 exemption |
| Ingest a batch of ≥20 actions (clean + planted violations) | ✅ 22-action combined batch |
| Pass/fail report with per-violation clause citation | ✅ |
| **One real Razorpay test-mode webhook sequence run through it** | ✅ **real test-mode payments captured and verified — score 60.0, 2 genuine failures** |
| Dashboard showing score and violation drill-down | ✅ |

### SHOULD

| Requirement | Status |
|---|---|
| LLM free-text parser | ⚠️ built + tested against a mocked provider; **never run against a live model** |
| Plain-English remediation | ⚠️ same |
| Versioned rule-pack file | ✅ |

### NICE

| Requirement | Status |
|---|---|
| Adaptive LLM scenario generator | ⚠️ scaffolded in `llm/scenario_gen.py`, never finished or run |
| Compliance-score trend across batches | ✅ built (`ScoreTrend`, renders at ≥3 reports) |

### Out of scope — correctly stayed out

No action execution, no voice pipeline, no generic hallucination/PII guardrail. ✅

---

## Functional requirements (`05-requirements.md` §5)

| | Requirement | Status | Evidence |
|---|---|---|---|
| FR1 | Accept a batch as structured JSON | ✅ | `test_api.py`, E2E |
| FR2 | Accept free text, parse via LLM | ✅ | **proven live 2026-09-02** — 6 actions parsed from prose, injection defeated |
| FR3 | Evaluate deterministically against the pack | ✅ | `test_rule_engine.py` golden batch |
| FR4 | Per-action PASS/FAIL + rule id, offending value, severity, clause+source | ✅ | `test_golden_every_violation_is_fully_cited` |
| FR5 | Aggregate compliance score | ✅ | `test_scoring`, base + weighted |
| FR6 | Plain-English explanation + remediation | ✅ | **proven live 2026-09-02** — real prose on all 5 violations |
| FR7 | Persist reports, list/retrieve | ✅ | Postgres store, `/reports` |
| FR8 | Serve the active rule-pack | ✅ | `/rules`, `/rules` page |
| FR9 | FASTag/NCMC exemption must PASS | ✅ | `test_fastag_exemption_makes_a_short_notice_debit_pass` + E2E |

**7 of 9 fully done. FR2 and FR6 are code-complete and mock-tested but have never touched a
real model** — that is one API key away, not one feature away.

## Non-functional requirements (§6)

| | Requirement | Status |
|---|---|---|
| NFR1 | Auditability — every verdict traceable, none from the LLM | ✅ enforced by `test_isolation.py` (AST walk) |
| NFR2 | Determinism — same input ⇒ same verdicts, no network in the engine | ✅ + idempotency proven over HTTP |
| NFR3 | Graceful degradation — LLM failure never blocks verdicts | ✅ `test_explainer_failure_degrades_instead_of_raising` |
| NFR4 | Updatability — rules change via YAML, engine untouched | ✅ closed condition vocabulary |
| NFR5 | Latency — 20-action batch well under a second | ✅ **67µs** for 22 actions, ~10,000× the requirement |
| NFR6 | Safety — report-only, no execution, no blocking | ✅ nothing in the codebase can move money |

**6 of 6.**

---

## Deliverables checklist (§8)

| Deliverable | Status |
|---|---|
| Public GitHub repo, clean README with architecture diagram + the "wall" explanation | ⚠️ README written; **repo has zero commits and is not pushed** |
| Green test suite (golden + isolation visible) | ✅ 175 + 23 |
| Working `/verify/batch` over both JSON and free text | ⚠️ JSON proven; free text unproven live |
| Dashboard: score + violation drill-down + rule viewer | ✅ |
| One real Razorpay test-mode webhook sequence | ✅ `razorpay_webhooks_real.json` + 9 tests |
| Measured result stated plainly | ✅ README §Measured results |
| 5-minute pitch + architecture walkthrough | ⚠️ script written (`06-pitch.md`); **not rehearsed, not recorded** |

---

## Beyond the spec — built anyway

Things not asked for that turned out to matter:

- **Razorpay webhook adapter** (`adapters/razorpay.py`) + `format: "razorpay"` — deterministic,
  no model, output still crosses the membrane.
- **Injection E2E suite** — runs the injected log against a model that *fully obeys* the
  injection, proving no false PASS is reachable. This was the pitch's best moment and was
  previously untested.
- **Latency benchmark** (`scripts/bench_verify.py`) — the number behind the pre-flight framing.
- **PWA** — manifest, icons, service worker that **never caches a verdict**, offline page that
  says "nothing was checked" rather than implying success.
- **Charts** — severity mix, violations-by-rule, and a 24h IST action timeline that draws the
  quiet-hours window so the rule is visible, not just the verdict.
- **Full design system** — light/dark tokens, validated severity ramp, motion, accessible
  listbox, Raleway/Open Sans.
- **23 browser E2E tests** committed to the repo.

---

## Spec-by-spec audit

Re-checked line by line on 2026-08-24.

| Doc | Requirement | Status |
|---|---|---|
| `00-overview.md` | Repository structure (every file listed) | ✅ all present |
| `01-architecture.md` §5 | Correlation id, idempotency key, budget pre-check at the gateway | ✅ |
| `01-architecture.md` §5 | **`auth (API key / tenant)` at the gateway** | ✅ **built 2026-09-02** — `api/_auth.py`, tenant-scoped reads, 404 on cross-tenant |
| `01-architecture.md` §7 | 5 eval signals: tool-call validity, injection heuristic, membrane rejection, trajectory cost, parse coverage | ✅ all 5 |
| `02-system-design.md` §B.4 | 4 tables: runs, reports, action_audit, raw_logs | ✅ + append-only triggers |
| `02-system-design.md` Part C | 8 test types: per-condition, golden, isolation, membrane, budget, idempotency, least-privilege, exemption | ✅ all 8 |
| `03-backend.md` §1 | 10 endpoints | ✅ all 10 |
| `04-frontend.md` §1 | 4 routes | ✅ + `/offline` |
| `04-frontend.md` §2 | 6 components | ✅ all 6 (plus 10 more) |
| `04-frontend.md` §4 | 5 states: empty, loading, success, partial, error | ✅ all 5 |
| `04-frontend.md` §6 | Typed API client mirroring backend types | ✅ superset |
| `04-frontend.md` §7 | Token palette, mono citations | ✅ |
| `04-frontend.md` §8 | Build order | ✅ followed |

**The specs are essentially fully implemented.** What is missing is evidence (§1–§3 below) and
one control that was specified but never built:

### The auth gap — found 2026-08-24

`01-architecture.md` promises `auth (API key / tenant)` at the gateway, and `tenant_id` is
threaded all the way through: `X-Tenant-Id` header → `VerifyRequest` → `Run` → a `tenant_id`
column on `runs`.

**Nothing enforces it.** No repository query filters by tenant — `list_reports`, `get_report`,
`get_run` and `get_audit` all return any row to any caller. The tenant header is decorative,
and any caller can read any tenant's compliance reports and audit trails by guessing an id.

Recommended fix is narrow, not a full auth system: an API-key→tenant mapping resolved at the
gateway, tenant-scoped repository queries, and **404 rather than 403** on a cross-tenant read
so the response does not confirm that the report exists. It should degrade to open when no keys
are configured, so the demo and the test suite stay frictionless. ~2 hours.

Priority: below OPEN-2. A wrong regulatory threshold discredits the tool; an unenforced tenant
boundary on a single-tenant demo does not.

### Deliberate deviations from the spec

| Spec says | What was built | Why |
|---|---|---|
| `04-frontend.md` §5: "Framer Motion, used sparingly… no decorative animation" | A full motion system — entrance stagger, count-up, hover/press micro-interactions, ambient depth layer | Explicitly requested. Still GPU-safe, reduced-motion honoured, nothing loops. |
| `04-frontend.md` §7: "consult the `frontend-design` skill" | Used `senior-frontend` + `dataviz` | That skill does not exist in this environment (OPEN-3). |
| `03-backend.md` §2: four route modules | Five — added `routes_runs.py` | §1 specifies three `/runs/*` endpoints that had nowhere else to live. |

---

## What I need from you

Everything below is blocked and cannot be moved without you.

| # | Need | Why it blocks |
|---|---|---|
| ~~1~~ | ~~**RBI/DPSS/2026-27/396** circular~~ | ✅ **DONE 2026-09-02** — circular located and read; 3 defects found and fixed (missing §8(b) carve-out, retry cap off by one, contact hours wrong at both ends). Two NPCI/FPC values corrected from secondary sources and still flagged. |
| ~~2~~ | ~~Razorpay capture~~ | ✅ **DONE** — 5 real payments, PII stripped, 9 tests |
| ~~3~~ | ~~**`OPENAI_API_KEY`** / OPEN-1~~ | ✅ **DONE 2026-09-02** — key added; injected log run live end-to-end (6 actions parsed, 5 violations, FASTag exemption held, ₹0.074/run). OPEN-1 closed: OpenAI, deliberately not the Agent SDK. |
| ~~4~~ | ~~Tagline decision~~ | ✅ **DONE 2026-09-02** — standardised on the artwork's *"Compliance for AI payment agents"*; `layout.tsx` and `manifest.ts` updated to match. |
| 5 | Go-ahead to **commit** | You asked me not to. ~115 files staged-ready. |

---

## Known issues

| Issue | Severity | Note |
|---|---|---|
| ~~Tenant isolation unenforced~~ | ✅ **FIXED 2026-09-02** | `API_KEYS` maps key→tenant at the gateway; `get_report`, `list_reports`, `count_reports`, `get_run`, `get_audit` and the idempotency lookup are all tenant-scoped; cross-tenant reads return **404, not 403**, so the response does not confirm the row exists. Degrades to open when unconfigured, so the demo and suite need no setup. 4 tests pin it. |
| **Repo lives inside OneDrive** | **High** | Has already caused: two `EINVAL: readlink` build crashes, and a test file silently dehydrated into a cloud placeholder so **14 tests vanished from the suite with no error**. Move the repo out, or set the folder to "Always keep on this device". `scripts/frontend.ps1` now auto-recovers the build case. |
| Eval signals do not survive a backend restart | Low | The sink is in-memory by design (MVP). Verdicts and audit trails are durable; signals are not. |
| Explanations are keyed by `action_id` | Low | Per `03-backend.md` §3. An action with two violations gets the same prose on both. Key by `(action_id, rule_id)` if a rule ever double-fires. |
| `scenario_gen.py` never run | Low | NICE-tier; first on the cut list per §7. |
| Docker never built | Low | `docker-compose.yml` and both Dockerfiles are written but `docker compose build` has never been run. |

---

## Suggested order from here

1. **OPEN-2** — verify the 5 regulatory values. Nothing else changes the project's credibility as much.
2. **Commit and push.** The "public repo" deliverable is unmet and it is one command away.
3. **Capture real Razorpay webhooks** — closes the last MUST-tier gap.
4. **Add a key and run the free-text path once**, including `injected_log.txt`, to convert FR2/FR6 from claims into demonstrations.
5. **Decide OPEN-1**, then align the pitch language.
6. **Rehearse and record** using `06-pitch.md`.

AI-specific work is tracked separately in [`07-ai-workflow.md`](07-ai-workflow.md).
