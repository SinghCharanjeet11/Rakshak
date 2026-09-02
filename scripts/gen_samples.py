import json
from pathlib import Path

SEED = Path("backend/app/seed")
OUT = Path("frontend/lib/samples.ts")

clean = json.loads((SEED / "clean_actions.json").read_text(encoding="utf-8"))
violating = json.loads((SEED / "violating_actions.json").read_text(encoding="utf-8"))
rzp = json.loads((SEED / "razorpay_webhooks.json").read_text(encoding="utf-8"))
# Real capture, if the user has run scripts/fetch_razorpay.py. Optional so a fresh clone
# without Razorpay credentials still generates a working sample set.
real_path = SEED / "razorpay_webhooks_real.json"
rzp_real = json.loads(real_path.read_text(encoding="utf-8")) if real_path.exists() else None
injected = (SEED / "injected_log.txt").read_text(encoding="utf-8")

def js(obj, indent=2):
    return json.dumps(obj, indent=indent, ensure_ascii=False)

header = '''/**
 * Demo fixtures, mirrored from `backend/app/seed/`.
 *
 * GENERATED — do not hand-edit. Regenerate after changing a seed file:
 *   python scripts/gen_samples.py
 *
 * These live in the bundle rather than being fetched so the demo never depends on a
 * second round-trip, and so `/verify` is useful before any backend call succeeds.
 */

import type { SubmitFormat } from "./api";

export interface Sample {
  id: string;
  label: string;
  blurb: string;
  format: SubmitFormat;
  /** What this fixture is meant to prove when it lands on the report page. */
  expect: string;
  body: string;
}

'''

samples = [
    ("violating", "Planted violations", "10 actions, 6 planted breaches, plus a FASTag debit that must PASS via exemption.", "json",
     "Score 40.0 — six failures, each citing its clause, and a_v07 passing as exempt.", js(violating)),
    ("clean", "Clean batch", "12 fully-compliant actions, including three boundary cases.", "json",
     "Score 100.0 and zero false positives.", js(clean)),
    ("razorpay", "Razorpay webhooks", "A webhook sequence mapped to actions by the deterministic adapter.", "razorpay",
     "6 actions from 7 events, 3 violations. The downtime event is ignored, not forced.", js(rzp)),
    ("injected", "Prompt-injected log", "Free text carrying an embedded instruction to mark everything compliant.", "text",
     "The injection lands in the parser; the deterministic core returns the correct failures anyway. Needs OPENAI_API_KEY.", None),
]

# Real capture, when the user has run scripts/fetch_razorpay.py. Placed third so it sits
# beside the synthetic Razorpay sample for comparison.
if rzp_real is not None:
    samples.insert(2, (
        "razorpay-real",
        "Razorpay — real account",
        "Real test-mode payments pulled from a live Razorpay account.",
        "razorpay",
        "Razorpay captured the Rs 20,000 payment happily; Rakshak fails it for missing AFA. "
        "An older payment with no compliance notes fails for want of a pre-debit notice.",
        js(rzp_real),
    ))

lines = [header, "export const SAMPLES: Sample[] = [\n"]
for sid, label, blurb, fmt, expect, body in samples:
    lines.append("  {\n")
    lines.append(f"    id: {json.dumps(sid)},\n")
    lines.append(f"    label: {json.dumps(label)},\n")
    lines.append(f"    blurb: {json.dumps(blurb)},\n")
    lines.append(f"    format: {json.dumps(fmt)},\n")
    lines.append(f"    expect: {json.dumps(expect)},\n")
    if body is None:
        lines.append(f"    body: {json.dumps(injected)},\n")
    else:
        lines.append("    body: " + json.dumps(body) + ",\n")
    lines.append("  },\n")
lines.append("];\n")

OUT.write_text("".join(lines), encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
