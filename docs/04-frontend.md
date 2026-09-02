# Rakshak — Frontend (Next.js Dashboard)

Next.js 14 (App Router), TypeScript, Tailwind CSS. A focused compliance dashboard: upload or paste an agent log, run verification, read the score and per-action verdicts, and inspect the rule-pack. This plays directly to your existing stack (Next.js 14 + TS + Tailwind + Framer Motion).

Design intent: this is a *trust* instrument, not a marketing page. Restrained, dense, legible — a compliance officer's tool. High signal, low chrome. One accent color for FAIL, one for PASS, everything else neutral.

---

## 1. Pages (App Router)

| Route | File | Purpose |
|---|---|---|
| `/` | `app/page.tsx` | Dashboard home: recent reports, aggregate stats, CTA to verify |
| `/verify` | `app/verify/page.tsx` | Upload/paste a log, choose format + rule version, run |
| `/reports/[id]` | `app/reports/[id]/page.tsx` | Full report: score, action table, violation drill-down |
| `/rules` | `app/rules/page.tsx` | Rule-pack viewer: every rule, its clause, severity, condition |

---

## 2. Component inventory

**`UploadPanel.tsx`** — a textarea (paste) + file drop (`.json`/`.txt`), a format toggle (JSON / free-text), a rule-version select, and a "Run verification" button. Emits the request to `POST /verify/batch`. Shows a loading state while the pipeline runs (parsing can take a beat when free-text).

**`ComplianceScore.tsx`** — the headline. A large numeric score (0–100), a pass/fail count, and a severity breakdown (n critical / high / medium). Color-coded ring or bar. This is the first thing on the report page and the thing you point at in the demo.

**`ActionTable.tsx`** — one row per action: id, type, key fields (amount, timestamp), and a PASS/FAIL pill. FAIL rows are expandable and accent-colored. Sortable by status so failures float up.

**`ViolationCard.tsx`** — shown inside an expanded FAIL row or stacked below the table: rule title, severity tag, the offending value, the **clause + source circular** (this citation is the credibility moment — make it prominent, monospace), and the LLM explanation + remediation.

**`RulePackViewer.tsx`** — renders the loaded rule-pack: version, source, effective date, and each rule as a card (id, title, severity, applies-to, clause, human-readable condition). Communicates "these are inspectable, versioned, and cite the law."

**`api.ts`** — typed fetch client mirroring the backend `Report`, `Action`, `Violation` types. One source of truth for the API contract on the frontend.

---

## 3. Key screen: report detail (`/reports/[id]`)

Layout, top to bottom:

```
┌───────────────────────────────────────────────────────────┐
│  ComplianceScore   72.5 / 100   ·  14 pass · 6 fail        │
│                    2 critical · 3 high · 1 medium          │
│                    rule-pack 2026.04.21-1                  │
├───────────────────────────────────────────────────────────┤
│  ActionTable                                               │
│   ✔ a_001 notify   …                                        │
│   ✘ a_007 debit    ₹20,000   [expand]                      │
│        └ ViolationCard: AFA_ABOVE_THRESHOLD · critical      │
│           offending: amount 20000 > 15000, afa_present=false│
│           clause: RBI/DPSS/2026-27/396 §AFA-threshold       │
│           "Debits above ₹15,000 require an additional…"     │
│   ✔ a_009 debit (FASTag, MCC 4784)  — exempt, passes        │
└───────────────────────────────────────────────────────────┘
```

The FASTag exempt-pass row visible next to failures is a deliberate design choice: it shows the tool is nuanced, not trigger-happy.

---

## 4. States to handle

- **Empty** (home with no reports yet) — a clear "Run your first verification" CTA.
- **Loading** — skeletons; a distinct "parsing free-text log…" message when format is text (sets expectation for the LLM latency).
- **Success** — the report renders progressively; score first, then table.
- **Partial** — verdicts present but explanations missing (explainer failed): show verdicts normally with a subtle "explanation unavailable" note, never block the report. This mirrors the backend's graceful degradation.
- **Error** — schema-invalid input surfaces the 422 detail inline on the upload panel; a 502 shows "couldn't parse free text — try submitting structured JSON."

---

## 5. Interaction / motion

Framer Motion, used sparingly: FAIL rows expand with a short height/opacity transition; the score ring animates once on load. No decorative animation — restraint reinforces the "serious compliance tool" read. Respect `prefers-reduced-motion`.

---

## 6. API client contract (`lib/api.ts`)

```ts
export type Severity = "critical"|"high"|"medium"|"low";
export interface Violation {
  action_id: string; rule_id: string; title: string;
  severity: Severity; offending_value: string;
  clause: string; source: string; explanation?: string;
}
export interface Report {
  id: string; created_at: string; rulepack_version: string;
  score: number; passed: number; failed: number; summary: string;
  actions: unknown[]; violations: Violation[];
}
export async function verifyBatch(body: {
  format: "json"|"text"; payload: unknown; rulepack_version?: string;
}): Promise<Report> { /* fetch POST /api/v1/verify/batch */ }
export async function getReport(id: string): Promise<Report> { /* … */ }
export async function listReports(): Promise<Report[]> { /* … */ }
export async function getRules(): Promise<unknown> { /* … */ }
```

Set `NEXT_PUBLIC_API_BASE` to the backend URL; never embed the OpenAI key in the frontend.

---

## 7. Styling tokens (Tailwind)

- Neutral base (slate/zinc), one PASS color (emerald), one FAIL color (rose), severity tags in graded warmth (critical=rose, high=orange, medium=amber, low=slate).
- Monospace for clause citations and rule ids — signals "machine-checked, precise."
- Dense but breathable: generous row height in the action table, tight typography in cards.
- Consult the `frontend-design` skill before building for the environment's design tokens and to avoid a templated look.

---

## 8. Build order (frontend)

1. `api.ts` types + client (contract first).
2. `/verify` upload panel → can POST and log the response.
3. `/reports/[id]` with ComplianceScore + ActionTable → the demo spine.
4. ViolationCard drill-down with the clause citation.
5. `/rules` viewer.
6. `/` home with recent reports.
7. Motion + empty/loading/error states last.
