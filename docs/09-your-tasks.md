# Your tasks — everything blocked on you

> ✅ **Mostly historical as of 2026-09-02.** §1 (OPEN-2), §2 (Razorpay), §3 (model key +
> OPEN-1) and §4 (tagline) are all done. §0 was handled by pinning the folder rather than
> moving it. **§5 — commit and push — is the only item still open**, plus §6 (rehearse the
> pitch). The detail below is kept for the reasoning, not as a to-do list.

> Six things only you can do. Each has: why it blocks, exact steps, and a command that proves
> it worked. Nothing here needs me — do them in any order, though §0 and §1 come first.
>
> Rough total: **half a day**, and most of that is §1.

**Quick check of where you stand at any point:**

```powershell
cd c:\Users\ASUS\OneDrive\Desktop\Rakshak\Rakshak
curl http://localhost:8000/api/v1/health
```

`unverified_rule_values` should shrink to `[]` as you work through §1.

---

## THE MINIMUM PATH — clear the MVP and push

Of everything in this file, only **two** things actually stand between you and
"MVP complete, code pushed". Do these and stop; the rest is credibility polish you can add
afterwards.

| # | Blocker | Whose | Time |
|---|---|---|---|
| **A** | **One real Razorpay test-mode webhook sequence** — the only unmet MVP **MUST** | yours | ~40 min |
| **B** | **Say "commit"** — the repo has zero commits; "public GitHub repo" is deliverable #1 | yours (I run it) | 5 min |

Everything else on the MVP MUST list is already done and tested:

```
✅ rule engine, 6 rules + 1 exemption
✅ 22-action batch (clean + planted violations)
✅ pass/fail report, every failure cited to its clause
✅ dashboard: score, drill-down, rule viewer
❌ one real Razorpay webhook sequence   <-- A
```

### The one judgement call

**OPEN-2 (§1) is not on the MVP MUST list, but it matters more than the item that is.**

A wrong ₹15,000 threshold discredits the whole tool; a synthetic webhook fixture is a missing
demo asset. If you only have time for one, do **§1**, not **§2**.

Suggested order if you have half a day: **§0 → §1 → §2 → §5 (push) → §3 → §6.**
If you have one hour: **§2 → §5**, and push with the values still flagged unverified — the UI
already says so honestly, which is a defensible position to demo from.

---

## §0 — Move the repo out of OneDrive *(10 min, do this first)*

**Why it blocks:** this is not cosmetic. It has already caused, in one week:

- two builds crashing with `EINVAL: readlink`,
- and a test file silently dehydrated into a cloud placeholder, so **14 tests vanished from
  the suite reporting no error at all**.

That last one is the dangerous failure: tests that disappear without failing. Everything else
in this list is work; this one is a trap that will keep eating your time.

**Option A — move it (best).**

```powershell
# close VS Code and stop both servers first
Move-Item "c:\Users\ASUS\OneDrive\Desktop\Rakshak" "c:\dev\Rakshak"
cd c:\dev\Rakshak\Rakshak
```

Then reinstall the two ignored folders, since paths are baked into them:

```powershell
cd frontend; Remove-Item -Recurse -Force node_modules, .next -ErrorAction SilentlyContinue; npm install
cd ..\backend; Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

**Option B — if you must keep it in OneDrive.** Right-click the `Rakshak` folder → **Always
keep on this device**. This stops dehydration but not the sync churn during builds.

**Proves it worked:**

```powershell
Get-ChildItem -Recurse frontend\e2e | Select-Object Name, Attributes
```

Every row should say `Archive` only. If any says `ReparsePoint`, it is still a cloud placeholder.

---

## §1 — Verify the 5 regulatory values (OPEN-2) *(2–3 hours — the highest-value work left)*

**Why it blocks:** every threshold in the rule-pack came from research, not from the published
circular. A wrong number does not just produce a wrong verdict — it discredits the entire tool,
and it is the first thing a knowledgeable panel will probe. Your own risk register calls this
the top project risk.

Right now the app tells the truth about this: `/health`, the dashboard and `/rules` all show
"5 values pending verification". That is the honest state, but it is not a good place to
finish.

### What to verify

Source: **RBI/DPSS/2026-27/396** (RBI Digital Payments E-mandate Framework 2026) and the current
NPCI e-mandate / UPI Autopay guidelines.

| # | Rule | Value as encoded | What to confirm |
|---|---|---|---|
| 1 | `PRE_DEBIT_NOTICE_24H` | **24 hours** before debit | The notice window, and whether it is 24h or something else for recurring e-mandates. |
| 2 | `AFA_ABOVE_THRESHOLD` | **₹15,000** | The AFA threshold. Also check whether the rule is *above* ₹15,000 or *at and above* — we encode strictly greater, so a ₹15,000 debit currently passes without AFA. |
| 3 | `RETRY_CAP_PER_WINDOW` | **max 3** per window | **The one I would check hardest.** The retry cap, and what the "window" is (per day? per mandate cycle?). |
| ~~4~~ | `QUIET_HOURS` | ✅ **corrected to 08:00–19:00 IST** | RBI Fair Practices Code, not the e-mandate circular. Was wrong at both ends. Still `value_verified: false` — secondary sources only. |
| ~~5~~ | `EXEMPT_MCC_SKIP_NOTICE` | ✅ **7412 removed** | §6(d) exempts by *purpose* (FASTag/NCMC auto-replenishment) and names no MCC at all. 4784 kept as a documented proxy; 7412 had no basis. |

### How to record each one

Open `backend/app/rules/rbi_emandate_2026.yaml` and `backend/app/rules/npci_mandate.yaml`.
For each rule you confirm, change **two things**:

```yaml
  - id: AFA_ABOVE_THRESHOLD
    title: "Additional Factor of Authentication required above ₹15,000"
    applies_to: [debit]
    severity: critical
    clause: "RBI/DPSS/2026-27/396 §AFA-threshold"   # <- make this the REAL section number
    value_verified: true                             # <- was false
    verified_on: "2026-08-24"                        # <- add this line
    condition:
      kind: if_amount_gt_then_flag
      amount_field: amount
      threshold: 15000                               # <- correct the number if it is wrong
      required_flag: afa_present
```

If a value turns out to be **wrong**, change it. That is the whole point of rules being data —
you edit the YAML and no engine code changes.

If you cannot confirm one, **leave `value_verified: false`**. An honest unknown is fine; a
confident wrong number is not.

### Proves it worked

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q          # must stay green — 175 passed
curl http://localhost:8000/api/v1/health          # unverified_rule_values should shrink
```

⚠️ **If you change a threshold, a golden test may fail.** That is the regression trap doing its
job, not a bug. Update the expected set in `backend/tests/test_rule_engine.py` and the table in
`backend/app/seed/README.md` **in the same edit**, so the fixtures still say what they prove.
Tell me and I will do it if you would rather not touch the tests.

---

## §2 — Capture a real Razorpay webhook sequence *(45 min)*

**Why it blocks:** `00-overview.md` lists "one real Razorpay test-mode webhook sequence run
through it" as a **MUST**. The adapter and its golden test are done, but
`backend/app/seed/razorpay_webhooks.json` is synthetic — written to representative shapes, not
captured from a live account.

### Steps

1. Sign in at **dashboard.razorpay.com** and switch to **Test Mode** (toggle, top of the page).
2. Go to **Settings → Webhooks → Add New Webhook**.
3. For a URL, use a request bin — **https://webhook.site** gives you a throwaway URL instantly.
   Paste it in.
4. Subscribe to these events (these are the ones the adapter maps):
   - `subscription.charged`
   - `payment.failed`
   - `payment.captured`
   - `subscription.halted`
   - `payment.dispute.created` *(if available)*
5. Create a **test subscription / e-mandate** and let it charge, or use Razorpay's webhook
   **"Test" / "Send test payload"** button if your dashboard offers it.
6. On webhook.site, copy the **full JSON body** of each event you receive.

### Format it for Rakshak

Paste the events into an array under `events`:

```json
{
  "_source": "Captured from Razorpay test mode, 2026-08-24. Secrets redacted.",
  "events": [
    { "entity": "event", "event": "subscription.charged", "payload": { ... } },
    { "entity": "event", "event": "payment.failed",       "payload": { ... } }
  ]
}
```

Save as `backend/app/seed/razorpay_webhooks_real.json`.

**Redact before saving:** remove any `notes` you did not add yourself, and search the file for
`rzp_live`, `key_secret`, `signature`, and any real customer email or phone. Test-mode payloads
should not contain live secrets, but check rather than assume.

### About compliance evidence

Razorpay webhooks do **not** carry pre-debit-notice times or AFA status — nothing in
`subscription.charged` says whether a notice was sent. The adapter reads those from the
merchant-controlled `notes` map. So when you create the test subscription, add notes:

```
rakshak_notice_sent_at   2026-08-22T09:00:00+05:30
rakshak_debit_due_at     2026-08-24T09:00:00+05:30
rakshak_afa_present      false
```

If you cannot, that is fine and still realistic — actions with no notice evidence will FAIL
`PRE_DEBIT_NOTICE_24H`, which is the correct outcome and a good thing to show.

### Proves it worked

Open http://localhost:3000/verify → format **Razorpay** → paste the file → Run.

---

## §3 — Decide OPEN-1, and add a model key *(20 min)*

**Why it blocks two things at once.**

**(a) The SDK claim.** `01-architecture.md` builds the pitch on *"we built on the Claude Agent
SDK"* — the panel's own platform. The code calls **OpenAI**. A technical panel will read the
repo and find the mismatch, and it will land on your strongest slide.

Pick one:

- **Switch to the Claude Agent SDK.** Confined to `backend/app/llm/_provider.py` by design.
  Stronger pitch. Tell me and I will do it — it is roughly an hour.
- **Stay on OpenAI** and delete the SDK claims from the pitch, defending it as
  provider-agnostic instead. Also honest, weaker story.

`docs/06-pitch.md` has this in its **"Do not say"** list until you decide.

**(b) Proving FR2 and FR6.** Free-text parsing and plain-English explanations are code-complete
and tested against a mock, but have **never touched a live model**. Two of your headline
capabilities are currently claims.

### Steps

```powershell
cd c:\Users\ASUS\OneDrive\Desktop\Rakshak\Rakshak
Copy-Item .env.example .env
notepad .env      # set OPENAI_API_KEY=sk-...
```

Then restart the backend so it picks up the key.

**Cost:** a few thousand tokens per run on `gpt-4o-mini` — well under a tenth of a cent. A $5
budget covers the whole build and demo. There is a hard ₹5 per-run cap in the code regardless.

### Proves it worked

```powershell
curl http://localhost:8000/api/v1/health     # "llm_enabled": true
```

Then open http://localhost:3000/verify → load **Prompt-injected log** → format **Free text** →
Run. You should get real verdicts with prose explanations, and the injection should change
nothing. **That is your best 30 seconds of demo — and it has never been run live.**

---

## §4 — Settle the tagline *(2 min)*

Two different taglines are in use:

| Where | Text |
|---|---|
| Your logo artwork (baked into the PNG) | "Compliance for AI payment agents" |
| App metadata, README, page copy | "agent compliance verification" |

Pick one. If you pick the logo's wording, tell me and I will change the app copy to match —
the artwork cannot be edited, so the logo's version is the cheaper one to standardise on.

---

## §5 — Commit and push *(10 min)*

**Why it blocks:** "Public GitHub repo" is the first item on the §8 deliverables list, and the
repo currently has **zero commits**.

### Before you commit — check for secrets

```powershell
cd c:\Users\ASUS\OneDrive\Desktop\Rakshak\Rakshak
git status --short                      # .env must NOT appear
git check-ignore -v .env                # should print the .gitignore rule
Select-String -Path .env.example -Pattern "sk-[A-Za-z0-9]"   # must return nothing real
```

### Commit

```powershell
git add .
git status                              # ~115 files; no .venv, node_modules, .next, *.db
git commit -m "Rakshak: deterministic compliance verifier for payment agents"
git branch -M main
git push -u origin main
```

The remote is already set to `https://github.com/SinghCharanjeet11/Rakshak.git`.

### After pushing

Open the repo on GitHub and confirm: the README renders with the logo, the architecture diagram
is intact, and `.env` is **not** there.

---

## §6 — Rehearse and record the pitch *(1–2 hours, do last)*

Use `docs/06-pitch.md` — it is a full script with timings, the panel Q&A rehearsed, and a
**"Do not say"** list.

Before recording, make sure §1 and §3 are done, or the script's honesty notes still apply:
do not state a regulatory value as settled, do not claim the Claude Agent SDK, and do not call
the Razorpay fixtures real.

**Setup:** backend on :8000, frontend on :3000, `/verify` open with **Planted violations**
loaded but not yet run, a terminal in `backend/` ready to run `pytest -q`. Dark theme if the
projector is dim.

---

## Checklist

```
[ ] §0  Repo moved out of OneDrive (or "always keep on this device")
[ ] §1  All 5 regulatory values verified; value_verified: true + verified_on added
[ ] §1  pytest still green after any threshold change
[ ] §2  Real Razorpay webhook sequence captured, redacted, and run through /verify
[ ] §3  OPEN-1 decided (Claude Agent SDK vs OpenAI)
[ ] §3  OPENAI_API_KEY set; free-text + injected-log run live at least once
[ ] §4  Tagline standardised
[ ] §5  Committed and pushed; .env confirmed absent from GitHub
[ ] §6  Pitch rehearsed and recorded
```

Anything you would rather hand back to me — the test updates in §1, the SDK switch in §3, the
copy change in §4 — just say so.
