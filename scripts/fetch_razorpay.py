"""Pull real test-mode payments from the Razorpay API and shape them as webhook events.

Why this exists: Razorpay blocklists request-bin hostnames (webhook.site and friends), so
capturing a live webhook delivery can be impossible without a public HTTPS endpoint. This
takes the other route — the substantive half of a webhook *is* the payment entity, and that
can be fetched directly from the API.

What you get is honest but worth stating precisely:

  * the payment entities are REAL, from your own test-mode account
  * the surrounding `{"entity": "event", "event": ..., "payload": ...}` envelope is
    reconstructed here, because the API returns the entity without it

That is a genuine improvement on the synthetic fixture, and it is not the same as a captured
delivery. The generated file says so in its own `_source` field — do not describe it as a
captured webhook.

Usage — never put your secret on the command line, it lands in shell history:

    # in backend/.env  (already gitignored)
    RAZORPAY_KEY_ID=rzp_test_xxxxxxxx
    RAZORPAY_KEY_SECRET=xxxxxxxx

    python scripts/fetch_razorpay.py

Writes backend/app/seed/razorpay_webhooks_real.json
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / "backend" / ".env"
OUT = ROOT / "backend" / "app" / "seed" / "razorpay_webhooks_real.json"

API = "https://api.razorpay.com/v1"

# Razorpay payment status -> the webhook event that carries that status.
STATUS_TO_EVENT = {
    "captured": "payment.captured",
    "authorized": "payment.authorized",
    "failed": "payment.failed",
    "refunded": "payment.captured",
}

# Fields that can carry personal data. Removed before the file is written, because this
# ends up committed to a public repository.
PII_FIELDS = ("email", "contact", "customer_id", "card_id", "vpa", "bank_transaction_id")


def load_env() -> tuple[str, str]:
    """Read credentials from the process env, falling back to backend/.env."""
    key = os.environ.get("RAZORPAY_KEY_ID", "")
    secret = os.environ.get("RAZORPAY_KEY_SECRET", "")

    if (not key or not secret) and ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if k.strip() == "RAZORPAY_KEY_ID" and not key:
                key = v
            elif k.strip() == "RAZORPAY_KEY_SECRET" and not secret:
                secret = v

    if not key or not secret:
        sys.exit(
            "Missing credentials.\n\n"
            "Add these to backend/.env (it is gitignored):\n"
            "  RAZORPAY_KEY_ID=rzp_test_xxxxxxxx\n"
            "  RAZORPAY_KEY_SECRET=xxxxxxxx\n\n"
            "Find them in the Razorpay dashboard, in Test Mode:\n"
            "  Settings -> API Keys -> Generate Test Key"
        )

    if not key.startswith("rzp_test"):
        sys.exit(
            f"Refusing to run: {key[:12]}... is not a test key.\n"
            "This must only ever touch test mode — a live key would pull real customer data\n"
            "into a file destined for a public repo."
        )

    return key, secret


def get(path: str, key: str, secret: str) -> dict:
    token = base64.b64encode(f"{key}:{secret}".encode()).decode()
    req = urllib.request.Request(
        API + path, headers={"Authorization": f"Basic {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        sys.exit(f"Razorpay API returned {e.code}: {body}")
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach the Razorpay API: {e.reason}")


def redact(entity: dict) -> dict:
    out = {k: v for k, v in entity.items() if k not in PII_FIELDS}
    # keep merchant-set notes; they carry the rakshak_* compliance evidence
    if isinstance(out.get("notes"), dict):
        out["notes"] = {
            k: v for k, v in out["notes"].items() if k.startswith("rakshak_")
        }
    return out


def main() -> None:
    key, secret = load_env()
    print(f"Fetching test-mode payments with {key[:16]}…")

    data = get("/payments?count=25", key, secret)
    payments = data.get("items", [])
    if not payments:
        sys.exit(
            "No payments found on this account yet.\n\n"
            "Make one first: Razorpay Dashboard (Test Mode) -> Payment Links ->\n"
            "Create Payment Link, then pay it with test card 4111 1111 1111 1111.\n\n"
            "Add these Notes on the link so the compliance evidence comes through:\n"
            "  rakshak_notice_sent_at  2026-08-26T09:00:00+05:30\n"
            "  rakshak_debit_due_at    2026-08-28T09:00:00+05:30\n"
            "  rakshak_afa_present     false"
        )

    events = []
    for p in payments:
        event = STATUS_TO_EVENT.get(p.get("status", ""))
        if not event:
            continue
        events.append(
            {
                "entity": "event",
                "event": event,
                "contains": ["payment"],
                "created_at": p.get("created_at"),
                "payload": {"payment": {"entity": redact(p)}},
            }
        )

    if not events:
        sys.exit(
            f"Found {len(payments)} payment(s) but none in a mappable status "
            f"({', '.join(STATUS_TO_EVENT)}). Statuses seen: "
            f"{sorted({p.get('status') for p in payments})}"
        )

    OUT.write_text(
        json.dumps(
            {
                "_source": (
                    "Real payment entities fetched from the Razorpay test-mode API. "
                    "The webhook envelope around each is reconstructed, not captured — "
                    "Razorpay blocklists request-bin hostnames. PII redacted."
                ),
                "events": events,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    counts: dict[str, int] = {}
    for e in events:
        counts[e["event"]] = counts.get(e["event"], 0) + 1

    print(f"\nWrote {OUT.relative_to(ROOT)}")
    print(f"  {len(events)} events from {len(payments)} payments")
    for name, n in sorted(counts.items()):
        print(f"    {name:<22} {n}")

    with_notes = sum(1 for e in events if e["payload"]["payment"]["entity"].get("notes"))
    print(f"  {with_notes} carry rakshak_* compliance notes")
    if with_notes == 0:
        print(
            "\n  None carry compliance evidence, so every debit will FAIL "
            "PRE_DEBIT_NOTICE_24H\n  for lack of a notice. That is the correct verdict, but "
            "for a demo with a mix of\n  pass and fail, add rakshak_* Notes when creating the "
            "next payment link."
        )

    print("\nNow run it:  http://localhost:3000/verify  ->  format Razorpay  ->  paste the file")


if __name__ == "__main__":
    main()
