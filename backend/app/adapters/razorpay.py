"""Razorpay webhook -> Action adapter (05-requirements.md §7, Days 6-7).

A **deterministic** transformation: no LLM, no inference, no guessing. It renames fields
and converts units, nothing more. Its output still crosses the validation membrane like
any other input, so a mapping bug produces a rejected action rather than a bad verdict.

Two honest limitations, stated rather than papered over:

1. **Razorpay webhooks do not carry compliance evidence.** A `subscription.charged` event
   says a debit happened; it does not say whether a pre-debit notice preceded it, whether
   AFA was collected, or which attempt in the window this is. Those facts live with the
   merchant. The adapter reads them from Razorpay's merchant-controlled `notes` map under
   a `rakshak_*` prefix — see NOTE_KEYS. Where a merchant does not stamp them, the field is
   absent, and absence is judged on its own terms by the engine: a debit with no
   `notice_sent_at` FAILS `PRE_DEBIT_NOTICE_24H` because the notice cannot be evidenced.
   That is the correct outcome, not a false positive.

2. `retry_index` is only populated when the merchant stamps it or an invoice carries an
   attempt count. Absent, `RETRY_CAP_PER_WINDOW` cannot bite — the engine does not invent
   a count it was not given.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

# Razorpay event -> Rakshak action type. Events outside this map are ignored: an adapter
# that forces every webhook into an action would manufacture actions to judge.
EVENT_MAP: dict[str, str] = {
    "subscription.charged": "debit",
    "payment.captured": "debit",
    "payment.authorized": "debit",
    "invoice.paid": "debit",
    "payment.failed": "mandate_retry",
    "subscription.pending": "mandate_retry",
    "subscription.halted": "escalate",
    "subscription.cancelled": "escalate",
    "payment.dispute.created": "escalate",
}

# Merchant-stamped compliance evidence, read from Razorpay's `notes` map.
NOTE_KEYS = {
    "rakshak_notice_sent_at": "notice_sent_at",
    "rakshak_debit_due_at": "debit_due_at",
    "rakshak_window_start": "window_start",
    "rakshak_retry_index": "retry_index",
    "rakshak_afa_present": "afa_present",
    "rakshak_mcc": "mcc",
    "rakshak_dispute_active": "dispute_active",
    "rakshak_consent_opted_out": "consent_opted_out",
    "rakshak_channel": "channel",
}

_BOOL_FIELDS = {"afa_present", "dispute_active", "consent_opted_out"}
_INT_FIELDS = {"retry_index"}
_TIME_FIELDS = {"notice_sent_at", "debit_due_at", "window_start"}


class RazorpayAdapterError(Exception):
    """The payload was not a Razorpay webhook envelope at all."""


def _epoch_to_iso(value: Any) -> Optional[str]:
    """Razorpay timestamps are unix epoch seconds, UTC."""
    if not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()


def _paise_to_inr(value: Any) -> Optional[float]:
    """Razorpay amounts are in the smallest currency unit. 2000000 paise = Rs 20,000."""
    if not isinstance(value, (int, float)):
        return None
    return round(float(value) / 100.0, 2)


def _coerce_note(field: str, raw: Any) -> Any:
    """Notes values arrive as strings. Convert only where the schema needs it, and return
    None on anything unparseable so the membrane never sees a half-converted value."""
    if raw is None:
        return None
    if field in _BOOL_FIELDS:
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in ("true", "yes", "1"):
            return True
        if text in ("false", "no", "0"):
            return False
        return None
    if field in _INT_FIELDS:
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            return None
    if field in _TIME_FIELDS:
        text = str(raw).strip()
        if text.isdigit():
            return _epoch_to_iso(int(text))
        return text or None
    return str(raw).strip() or None


def _entity(event: dict[str, Any], name: str) -> dict[str, Any]:
    node = event.get("payload", {}).get(name, {})
    entity = node.get("entity") if isinstance(node, dict) else None
    return entity if isinstance(entity, dict) else {}


def map_event(event: dict[str, Any], index: int = 0) -> Optional[dict[str, Any]]:
    """One webhook envelope -> one Action dict (or None if the event is not an action)."""
    if not isinstance(event, dict):
        return None

    name = event.get("event")
    action_type = EVENT_MAP.get(name or "")
    if action_type is None:
        return None

    payment = _entity(event, "payment")
    subscription = _entity(event, "subscription")
    invoice = _entity(event, "invoice")
    primary = payment or invoice or subscription

    created = (
        payment.get("created_at")
        or invoice.get("created_at")
        or subscription.get("current_start")
        or event.get("created_at")
    )
    timestamp = _epoch_to_iso(created)
    if timestamp is None:
        # No usable time means nothing time-based can be judged. Dropping it is safer
        # than stamping "now" — a fabricated timestamp could manufacture a clean verdict.
        return None

    action: dict[str, Any] = {
        "id": primary.get("id") or f"rzp_{name}_{index}",
        "type": action_type,
        "timestamp": timestamp,
        "mandate_id": subscription.get("id") or invoice.get("subscription_id"),
        "customer_id": (
            subscription.get("customer_id")
            or invoice.get("customer_id")
            or payment.get("customer_id")
        ),
    }

    amount = _paise_to_inr(payment.get("amount") or invoice.get("amount"))
    if amount is not None:
        action["amount"] = amount
    currency = payment.get("currency") or invoice.get("currency")
    if currency:
        action["currency"] = currency

    # A dispute event is the one place Razorpay states a compliance-relevant fact directly.
    if name == "payment.dispute.created":
        action["dispute_active"] = True

    if action_type == "mandate_retry":
        attempts = invoice.get("attempts")
        if isinstance(attempts, int):
            action["retry_index"] = attempts

    # Merchant-stamped evidence wins over anything inferred above.
    notes: dict[str, Any] = {}
    for source in (payment, subscription, invoice):
        candidate = source.get("notes")
        if isinstance(candidate, dict):
            notes.update(candidate)

    for note_key, field in NOTE_KEYS.items():
        if note_key in notes:
            value = _coerce_note(field, notes[note_key])
            if value is not None:
                action[field] = value

    return {k: v for k, v in action.items() if v is not None}


def map_webhook_payload(payload: Any) -> list[dict[str, Any]]:
    """Accept a single webhook envelope, a list of them, or an {"events": [...]} wrapper."""
    if isinstance(payload, dict):
        if isinstance(payload.get("events"), list):
            events: Iterable[Any] = payload["events"]
        else:
            events = [payload]
    elif isinstance(payload, list):
        events = payload
    else:
        raise RazorpayAdapterError(
            f"expected a Razorpay webhook envelope or a list of them, "
            f"got {type(payload).__name__}"
        )

    events = list(events)
    if not events:
        raise RazorpayAdapterError("no webhook events in payload")
    if not any(isinstance(e, dict) and "event" in e for e in events):
        raise RazorpayAdapterError(
            "no 'event' key found — this does not look like a Razorpay webhook payload"
        )

    actions: list[dict[str, Any]] = []
    for i, event in enumerate(events):
        mapped = map_event(event, i)
        if mapped is not None:
            actions.append(mapped)
    return actions
