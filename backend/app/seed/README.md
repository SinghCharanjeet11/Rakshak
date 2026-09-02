# Seed data — what each action is for

The JSON files carry no inline comments on purpose: `Action` is `extra="forbid"` so that a
hallucinated field is *rejected* by the membrane rather than silently ignored (invariant I3),
and a `_comment` key would have forced that guarantee to be weakened. The commentary lives here.

These fixtures are the golden test's expected-output contract (`tests/test_rule_engine.py`).
**Editing them changes what the demo proves — update the golden assertions in the same commit.**

## `clean_actions.json` — 13 actions, 0 violations

Establishes the false-positive claim: *"zero false positives on the clean batch."*

| id | type | why it passes |
|---|---|---|
| `a_c01` | debit | 24h notice exactly — the boundary case, must pass |
| `a_c02` | debit | 48h notice, small amount |
| `a_c03` | debit | ₹14,999 — one rupee under the AFA threshold, no AFA needed |
| `a_c04` | debit | ₹18,000 **with** `afa_present: true` — over threshold, correctly authenticated |
| `a_c05` | debit | 96h notice |
| `a_c06` | mandate_retry | `retry_index: 1`, no dispute |
| `a_c07` | mandate_retry | `retry_index: 2`, no dispute |
| `a_c08` | notify | opted in |
| `a_c09` | notify | opted in |
| `a_c10` | contact | 10:45 IST — inside contact hours |
| `a_c11` | contact | 18:15 IST — near the closing edge of 08:00–19:00, still inside |
| `a_c12` | escalate | no rule applies to `escalate` |
| `a_c13` | debit | ₹50,000 insurance premium, **no AFA** — passes via §8(b) up to ₹1,00,000 |

`a_c01`, `a_c03`, `a_c11` and `a_c13` are deliberate boundary cases. They are the fixtures that
break first if someone "tidies" a comparison operator from `>=` to `>`.

`a_c13` earns its place: before 2026-09-02 the pack had no §8(b) carve-out, so a compliant
₹50,000 insurance premium was reported as a **critical AFA breach**. It is the regression
guard on the "zero false positives" claim, which that gap had quietly made untrue.

## `violating_actions.json` — 10 actions, 6 violations, 1 exempt pass

Each violating action trips **exactly one** rule. That is what lets the golden test assert an
exact violation set instead of a count, and it is why the demo can point at a row and name the
single reason it failed.

| id | expected verdict | rule |
|---|---|---|
| `a_v01` | FAIL | `RETRY_CAP_PER_WINDOW` — 5th attempt in window (NPCI permits 4: 1 + 3 retries) |
| `a_v02` | FAIL | `PRE_DEBIT_NOTICE_24H` — 2h notice; amount kept under ₹15,000 so AFA stays silent |
| `a_v03` | FAIL | `AFA_ABOVE_THRESHOLD` — ₹20,000, `afa_present: false`; notice a clean 48h |
| `a_v04` | FAIL | `NO_RETRY_UNDER_DISPUTE` — `retry_index: 1` so the cap stays silent |
| `a_v05` | FAIL | `QUIET_HOURS` — 23:30 IST, outside 08:00–19:00 |
| `a_v06` | FAIL | `RESPECT_OPT_OUT` — 11:30 IST so quiet hours stays silent |
| **`a_v07`** | **PASS** | **`EXEMPT_MCC_SKIP_NOTICE`** — FASTag (MCC 4784) with 2h notice |
| `a_v08` | PASS | filler, so the batch reads like a real log |
| `a_v09` | PASS | filler |
| `a_v10` | PASS | filler |

`a_v07` is the one to protect. It is a *short-notice debit that must pass*, and it is the
evidence that Rakshak is nuanced rather than trigger-happy — `04-frontend.md` §3 puts it on
screen directly beneath the failures for exactly that reason. If it ever flips to FAIL the
exemption resolver is broken, and the demo is dead.

Combined batch (both files, 23 actions, 6 failed) scores **73.91** on the base formula.

## `injected_log.txt` — the architecture money-shot

A free-text log carrying an embedded prompt-injection line telling the parser to mark
everything compliant. The injection lands in the ingestion subagent — the only component that
ever sees prose — and the deterministic core, which sees only schema-valid `Action` objects,
returns the correct failures regardless. Run it with `format: "text"`.

Expected: the injection changes nothing about the verdicts, and `injection_heuristic` fires as
a non-blocking eval signal.

## `razorpay_webhooks.json` — 7 events → 6 actions, 3 violations

Run it with `format: "razorpay"`. The adapter (`app/adapters/razorpay.py`) is a deterministic
rename-and-convert — no model — and its output still crosses the membrane.

| event | → | verdict |
|---|---|---|
| `subscription.charged` ₹499, 48h notice | `debit` | PASS |
| `subscription.charged` ₹20,000, no AFA | `debit` | FAIL `AFA_ABOVE_THRESHOLD` |
| `payment.failed`, dispute open | `mandate_retry` | FAIL `NO_RETRY_UNDER_DISPUTE` |
| `payment.failed`, 5th attempt | `mandate_retry` | FAIL `RETRY_CAP_PER_WINDOW` |
| `subscription.charged` MCC 4784, 2h notice | `debit` | PASS via exemption |
| `subscription.halted` | `escalate` | PASS (no rule applies) |
| `payment.downtime.started` | — | **ignored** — not an agent action |

> ⚠️ **These are synthetic**, written to representative Razorpay webhook shapes. They are kept
> because they exercise event types a card-only account cannot produce (`subscription.*`,
> `payment.dispute.created`) and because each action trips exactly one rule, which makes them a
> better golden fixture. **Real data now lives in `razorpay_webhooks_real.json`** — see below.

**Two limits worth knowing before the demo.** Razorpay webhooks do not carry compliance
evidence: nothing in `subscription.charged` says whether a pre-debit notice was sent or AFA
collected. The adapter reads those from the merchant-controlled `notes` map under a
`rakshak_*` prefix. Where a merchant stamps nothing, the field is *absent* — and a debit with
no `notice_sent_at` correctly FAILS, because a notice that cannot be evidenced is not a
notice. The adapter never defaults a missing value, and never stamps a missing timestamp with
"now", since either would manufacture a clean verdict out of thin air.

## `razorpay_webhooks_real.json` — REAL test-mode data

Generated by `scripts/fetch_razorpay.py` from a live Razorpay **test-mode** account. Payment
entities are genuine; the `{"entity":"event", ...}` envelope around each is reconstructed,
because Razorpay blocklists request-bin hostnames so a webhook delivery could not be captured.
The file states this in its own `_source` field — **do not describe it as a captured webhook.**

PII (email, contact, card and customer ids) is stripped at generation; only `rakshak_*` notes
are kept. Verified clean: no email, phone or card number in the committed file.

Current capture scores **60.0** — 5 actions, 2 failures:

| Payment | Verdict |
|---|---|
| ₹20,000 captured, `rakshak_afa_present: false` | **FAIL** `AFA_ABOVE_THRESHOLD` |
| ₹500 captured, 48h notice stamped | PASS |
| ₹500 failed | PASS (maps to `mandate_retry`) |
| ₹149 captured, **no compliance notes** | **FAIL** `PRE_DEBIT_NOTICE_24H` — notice absent |
| ₹149 failed | PASS |

The first row is the demo: **Razorpay processed that ₹20,000 payment happily. Rakshak says it
breached.** Payment success and compliance are different questions, and that is the product.

Tested by `tests/test_razorpay_real.py`, which asserts **invariants rather than a fixed
expected set** — regenerating the fixture with more payments must not break the suite. The
suite skips itself if the file is absent, so a clone without Razorpay credentials still runs green.
