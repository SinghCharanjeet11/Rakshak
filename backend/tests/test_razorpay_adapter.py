"""Razorpay webhook -> Action adapter (05-requirements.md §7, Days 6-7).

The adapter is deterministic, so it is tested like the engine: exact expected output, not
"roughly right". Its most important property is what it *refuses* to do — invent evidence
the webhook does not contain.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.adapters.razorpay import (
    RazorpayAdapterError,
    map_event,
    map_webhook_payload,
)
from app.config import settings
from app.core.rule_engine import evaluate_detailed
from app.main import app
from tests.conftest import SEED_DIR

API = settings.API_PREFIX


def fixture() -> dict:
    return json.loads((SEED_DIR / "razorpay_webhooks.json").read_text(encoding="utf-8"))


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------
# unit
# --------------------------------------------------------------------------


def test_amounts_convert_from_paise():
    """2000000 paise is Rs 20,000 — above the AFA threshold. Getting this wrong by 100x
    would silently move actions across a regulatory boundary."""
    events = fixture()["events"]
    action = map_event(events[1])
    assert action is not None
    assert action["amount"] == 20000.00


def test_timestamps_convert_from_epoch_seconds():
    action = map_event(fixture()["events"][0])
    assert action is not None
    assert action["timestamp"] == "2026-08-20T03:30:00+00:00"  # 09:00 IST


def test_unmapped_events_are_ignored_not_forced():
    """`payment.downtime.started` is not an agent action. An adapter that manufactured
    one would give the engine something fictional to judge."""
    assert map_event(fixture()["events"][6]) is None


def test_merchant_notes_supply_the_compliance_evidence():
    action = map_event(fixture()["events"][0])
    assert action is not None
    assert action["notice_sent_at"] == "2026-08-18T09:00:00+05:30"
    assert action["afa_present"] is False


def test_note_values_are_coerced_to_their_schema_types():
    action = map_event(fixture()["events"][3])
    assert action is not None
    assert action["retry_index"] == 5  # int, not "5"
    assert action["dispute_active"] is False  # bool, not "false"


def test_unparseable_note_is_dropped_rather_than_half_converted():
    event = {
        "event": "subscription.charged",
        "created_at": 1787196600,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_x",
                    "created_at": 1787196600,
                    "notes": {"rakshak_retry_index": "many", "rakshak_afa_present": "maybe"},
                }
            }
        },
    }
    action = map_event(event)
    assert action is not None
    assert "retry_index" not in action
    assert "afa_present" not in action


def test_event_without_a_usable_timestamp_is_dropped():
    """Stamping "now" would fabricate a fact that time-based rules then judge."""
    assert map_event({"event": "subscription.charged", "payload": {}}) is None


def test_dispute_event_states_the_fact_directly():
    event = {
        "event": "payment.dispute.created",
        "created_at": 1787221800,
        "payload": {"payment": {"entity": {"id": "pay_d", "created_at": 1787221800}}},
    }
    action = map_event(event)
    assert action is not None and action["dispute_active"] is True


def test_missing_evidence_is_absent_not_defaulted():
    """A debit whose merchant stamped no notice must come out with no `notice_sent_at`,
    so the engine fails it for lack of evidence rather than passing it on a default."""
    event = {
        "event": "subscription.charged",
        "created_at": 1787196600,
        "payload": {
            "payment": {"entity": {"id": "pay_bare", "amount": 100000, "created_at": 1787196600}}
        },
    }
    action = map_event(event)
    assert action is not None
    assert "notice_sent_at" not in action
    assert "afa_present" not in action


def test_accepts_a_bare_envelope_a_list_and_a_wrapper():
    events = fixture()["events"]
    assert len(map_webhook_payload(events[0])) == 1
    assert len(map_webhook_payload(events)) == 6
    assert len(map_webhook_payload({"events": events})) == 6


def test_non_webhook_payload_raises():
    with pytest.raises(RazorpayAdapterError, match="does not look like"):
        map_webhook_payload([{"id": "a_1", "type": "debit"}])
    with pytest.raises(RazorpayAdapterError, match="no webhook events"):
        map_webhook_payload([])
    with pytest.raises(RazorpayAdapterError, match="expected a Razorpay webhook"):
        map_webhook_payload("subscription.charged")


# --------------------------------------------------------------------------
# golden: the whole sequence through the real engine
# --------------------------------------------------------------------------


def test_golden_webhook_sequence(pack):
    from app.core.models import Action

    actions = [Action.model_validate(a) for a in map_webhook_payload(fixture())]
    assert len(actions) == 6

    result = evaluate_detailed(actions, pack)
    assert {(v.action_id, v.rule_id) for v in result.violations} == {
        ("pay_RZP0000000002", "AFA_ABOVE_THRESHOLD"),
        ("pay_RZP0000000003", "NO_RETRY_UNDER_DISPUTE"),
        ("pay_RZP0000000004", "RETRY_CAP_PER_WINDOW"),
    }
    assert [e.action_id for e in result.exemptions_applied] == ["pay_RZP0000000005"]


def test_razorpay_format_end_to_end(client, clean_db):
    r = client.post(
        f"{API}/verify/batch", json={"format": "razorpay", "payload": fixture()}
    )
    assert r.status_code == 200
    body = r.json()

    assert len(body["actions"]) == 6
    assert body["failed"] == 3
    assert body["passed"] == 3
    assert body["score"] == 50.0
    assert body["run_id"] == r.headers["X-Run-Id"]


def test_razorpay_payload_that_is_not_a_webhook_is_422(client, clean_db):
    r = client.post(
        f"{API}/verify/batch",
        json={"format": "razorpay", "payload": [{"id": "a", "type": "debit"}]},
    )
    assert r.status_code == 422


def test_razorpay_run_is_replayable(client, clean_db):
    """Reproducibility holds across the adapter: the raw webhook is what gets stored."""
    first = client.post(
        f"{API}/verify/batch", json={"format": "razorpay", "payload": fixture()}
    )
    run_id = first.headers["X-Run-Id"]

    replayed = client.post(f"{API}/runs/{run_id}/replay")
    assert replayed.status_code == 200
    assert replayed.json()["id"] == first.json()["id"]
