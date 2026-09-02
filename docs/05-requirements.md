# Rakshak — Requirements, Setup & Build Plan

## 1. Tech stack

**Backend:** Python 3.11+, FastAPI, Uvicorn, Pydantic v2, PyYAML, OpenAI Python SDK (`gpt-4o-mini`), SQLite (default) or Postgres, pytest.
**Frontend:** Node 18+, Next.js 14 (App Router), TypeScript, Tailwind CSS, Framer Motion.
**Infra:** Docker + docker-compose (optional but nice for the demo), a single OpenAI API key.
**External:** Razorpay test-mode account (only to capture real webhook payload fixtures — no live calls during the demo).

**Cost:** the only paid dependency is the OpenAI API, and usage here is tiny — structured extraction over a ~20-action log plus a batched explanation call, a few thousand tokens per verification run. At `gpt-4o-mini` rates that's well under a tenth of a cent per run; a $5 budget covers thousands of runs across the whole build, testing, and live demo. Everything else (FastAPI, Next.js, Tailwind, SQLite, Razorpay test mode) is free.

---

## 2. Dependencies

`backend/pyproject.toml` (key deps):
```
fastapi, uvicorn[standard], pydantic>=2, pyyaml, openai>=1.0, python-dotenv
sqlmodel        # or sqlite3 stdlib + a thin repo
pytest, httpx   # httpx for TestClient
```

`frontend/package.json` (key deps):
```
next@14, react, react-dom, typescript
tailwindcss, postcss, autoprefixer
framer-motion
```

---

## 3. Environment variables

`.env.example`:
```
# backend
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
DATABASE_URL=postgresql://...-pooler.<region>.aws.neon.tech/neondb?sslmode=require
ACTIVE_RULEPACK=2026.04.21-1
FRONTEND_ORIGIN=http://localhost:3000
# frontend
NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1
```

Never commit the real `.env`. The frontend gets only `NEXT_PUBLIC_*` values.

---

## 4. Setup & run

```bash
# clone
git clone <repo> rakshak && cd rakshak
cp .env.example .env         # fill OPENAI_API_KEY

# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8000
pytest -q                    # should be green

# frontend (new terminal)
cd ../frontend
npm install
npm run dev                  # http://localhost:3000

# or everything at once
docker-compose up --build
```

Smoke test: open `/verify`, paste `seed/violating_actions.json`, run → report shows the expected failures with clause citations.

---

## 5. Functional requirements (MVP)

- FR1: Accept a batch of actions as structured JSON.
- FR2: Accept a batch as free text and parse it to structured actions via the LLM.
- FR3: Evaluate each action against the active rule-pack deterministically.
- FR4: Return a per-action PASS/FAIL with, for each FAIL, the rule id, offending value, severity, and clause+source citation.
- FR5: Compute and return an aggregate compliance score.
- FR6: Generate a plain-English explanation + remediation per violation (LLM).
- FR7: Persist reports and list/retrieve them.
- FR8: Serve the active rule-pack for inspection.
- FR9: Correctly apply the FASTag/NCMC exemption (an exempt action must PASS).

## 6. Non-functional requirements

- NFR1 (auditability): every verdict traceable to a rule + clause; no verdict from the LLM.
- NFR2 (determinism): identical input ⇒ identical verdicts; engine has no network/LLM imports.
- NFR3 (graceful degradation): LLM failure never blocks verdicts.
- NFR4 (updatability): rules changeable via the YAML pack without touching engine code.
- NFR5 (latency): a 20-action structured batch verifies in well under a second (LLM explain adds a few seconds, batched into one call).
- NFR6 (safety): no action execution, no blocking — report-only, defense-only.

---

## 7. 14-day build plan (to Sept 5)

**Days 1–2 — foundations.** Repo scaffold, Pydantic models, rule-pack schema, load+validate. Verify every RBI/NPCI numeric value against the source circular and lock them into the YAML. Write the two rule-pack files.

**Days 3–5 — the engine (the graded core).** Implement each condition evaluator with unit tests. Build `evaluate()`, exemptions, scoring. Write the golden seed-batch test and the isolation test. This must be rock-solid before anything else.

**Days 6–7 — API.** FastAPI endpoints, repository/persistence, `/verify/batch` end to end with structured JSON. Capture real Razorpay test-mode webhook payloads into fixtures and add a small adapter that maps them to `Action`s.

**Days 8–9 — LLM layer.** Ingestion agent (free-text → actions) using OpenAI's `json_object` mode + re-validation wall; explanation agent (batched). Graceful-degradation paths. `temperature=0` for ingestion.

**Days 10–12 — frontend.** Build in the order in `04-frontend.md`: api client → verify page → report detail (score + table) → violation drill-down → rules viewer → home. Wire to the live backend.

**Day 13 — polish + demo data.** Curate the seed batch so the demo tells a story (include the FASTag exempt-pass). Motion, empty/error states, README with architecture diagram.

**Day 14 — pitch + record.** 5-minute pitch script, architecture walkthrough, record the demo video, final repo hygiene (no secrets, green tests, clear README).

Buffer note: if time slips, cut the scenario generator and the severity-weighted score first; never cut the golden test or the clause citations.

---

## 8. Deliverables checklist (Track 02)

- [ ] Public GitHub repo, clean README with the architecture diagram and the "wall" explanation.
- [ ] Green test suite (golden + isolation tests visible).
- [ ] Working `/verify/batch` over both JSON and free text.
- [ ] Dashboard demoing score + violation drill-down + rule viewer.
- [ ] One real Razorpay test-mode webhook sequence run through the tool.
- [ ] Measured result stated plainly: "caught N/N planted violations; 0 false positives on the clean batch; FASTag exemption correctly passed."
- [ ] 5-minute pitch + architecture walkthrough.

---

## 9. Demo script (5 minutes)

1. **Problem (30s).** "Everyone — including Razorpay's Agent Studio — is shipping payment agents that *act*. A recovery agent can silently break RBI rules: retry a mandate too many times, debit without the 24-hour notice, skip AFA above ₹15,000. Who checks? Nobody — until Rakshak."
2. **Run (90s).** Paste a batch on `/verify`. Report renders: score 72.5, six failures. Expand the ₹20,000 debit → AFA violation citing `RBI/DPSS/2026-27/396`. Show the FASTag debit *passing* via exemption.
3. **Depth (90s).** Open `/rules` — the versioned rule-pack citing clauses. Then show the code: the deterministic engine and the green golden test. "The law is deterministic — I don't let a language model decide compliance. The LLM only parses messy logs and explains violations."
4. **Result + close (60s).** "Caught every planted violation, zero false positives, exemptions respected. Agent Studio builds the agents; Rakshak is the layer that keeps them compliant enough to ship. Every payment agent in India needs this."

---

## 10. Risks & mitigations

- **Wrong regulatory value** → discredits everything. Mitigation: verify against the circular on Day 1; keep values as cited data; state "verify current values" in the README.
- **LLM parser flakiness on stage** → Mitigation: demo primarily with structured JSON; free-text is the "and it also handles messy logs" bonus, with fixtures pre-tested.
- **Scope creep** → Mitigation: the MUST/SHOULD/NICE split; cut order defined in §7.
- **"Isn't this just guardrails?"** → Mitigation: rehearse the answer — generic guardrails do hallucination/PII; Rakshak encodes Indian payment regulation none of them touch.
