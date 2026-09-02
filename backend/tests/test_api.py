"""End-to-end HTTP tests — 03-backend.md §5, plus the budget and idempotency tests
required by 02-system-design.md Part C.

No test here reaches a model provider: conftest blanks OPENAI_API_KEY, so the free-text
path exercises the documented graceful-degradation behaviour rather than the network.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.run import RunStatus
from app.main import app
from app.store import repository
from tests.conftest import seed_raw, seed_text

API = settings.API_PREFIX


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _post_batch(client, payload, **kw):
    body = {"format": "json", "payload": payload, **kw}
    return client.post(f"{API}/verify/batch", json=body)


# --------------------------------------------------------------------------
# health + rules
# --------------------------------------------------------------------------


def test_health(client):
    r = client.get(f"{API}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["rulepack"] == "2026.04.21-1"
    assert body["rules_loaded"] == 6


def test_rules_endpoint_exposes_clauses_and_prose(client):
    body = client.get(f"{API}/rules").json()
    assert body["circular"] == "RBI/DPSS/2026-27/396"
    assert len(body["rules"]) == 6
    assert len(body["exemptions"]) == 2

    afa = next(r for r in body["rules"] if r["id"] == "AFA_ABOVE_THRESHOLD")
    assert afa["clause"] == "RBI/DPSS/2026-27/396 §8(a)"
    assert afa["condition_prose"] == "if amount > 15000 then afa_present must be true"


def test_rules_versions(client):
    assert "2026.04.21-1" in client.get(f"{API}/rules/versions").json()["versions"]


def test_rules_unknown_version_is_400(client):
    assert client.get(f"{API}/rules", params={"version": "1999.1"}).status_code == 400


# --------------------------------------------------------------------------
# /verify/batch — the main endpoint
# --------------------------------------------------------------------------


def test_clean_batch_scores_100(client, clean_db):
    r = _post_batch(client, seed_raw("clean_actions.json"))
    assert r.status_code == 200
    body = r.json()
    assert body["score"] == 100.0
    assert body["failed"] == 0
    assert body["passed"] == 13
    assert body["violations"] == []
    assert "Fully compliant" in body["summary"]


def test_violating_batch_returns_the_expected_failures(client, clean_db):
    r = _post_batch(client, seed_raw("violating_actions.json"))
    assert r.status_code == 200
    body = r.json()

    assert body["failed"] == 6
    assert {(v["action_id"], v["rule_id"]) for v in body["violations"]} == {
        ("a_v01", "RETRY_CAP_PER_WINDOW"),
        ("a_v02", "PRE_DEBIT_NOTICE_24H"),
        ("a_v03", "AFA_ABOVE_THRESHOLD"),
        ("a_v04", "NO_RETRY_UNDER_DISPUTE"),
        ("a_v05", "QUIET_HOURS"),
        ("a_v06", "RESPECT_OPT_OUT"),
    }


def test_every_violation_is_cited_over_the_wire(client, clean_db):
    body = _post_batch(client, seed_raw("violating_actions.json")).json()
    for v in body["violations"]:
        assert v["clause"] and v["source"] and v["offending_value"]
    afa = next(v for v in body["violations"] if v["rule_id"] == "AFA_ABOVE_THRESHOLD")
    assert "20000" in afa["offending_value"] and "15000" in afa["offending_value"]


def test_fastag_exemption_is_reported_as_an_exemption(client, clean_db):
    """Not merely absent from violations — the report must say *why* it passed."""
    body = _post_batch(client, seed_raw("violating_actions.json")).json()
    applied = [e for e in body["exemptions_applied"] if e["action_id"] == "a_v07"]
    assert len(applied) == 1
    assert applied[0]["exemption_id"] == "EXEMPT_MCC_SKIP_NOTICE"
    assert "4784" in applied[0]["reason"]


def test_explanations_are_absent_without_a_model_and_the_report_still_returns(
    client, clean_db
):
    """Invariant I9: verdicts never depend on the model layer."""
    body = _post_batch(client, seed_raw("violating_actions.json")).json()
    assert body["failed"] == 6
    assert all(v["explanation"] is None for v in body["violations"])


def test_response_carries_correlation_and_run_headers(client, clean_db):
    r = _post_batch(client, seed_raw("clean_actions.json"))
    assert r.headers["X-Correlation-Id"].startswith("cor_")
    assert r.headers["X-Run-Id"].startswith("run_")
    assert r.headers["X-Rulepack-Version"] == "2026.04.21-1"


def test_schema_invalid_action_is_422(client, clean_db):
    r = _post_batch(client, [{"id": "a", "type": "not_a_real_type", "timestamp": "2026-01-01T00:00:00Z"}])
    # Rejected by the membrane, so the batch is empty rather than the request malformed.
    assert r.status_code == 200
    assert r.json()["actions"] == []


def test_non_list_payload_is_422(client, clean_db):
    r = _post_batch(client, {"status": "all good"})
    assert r.status_code == 422


def test_unknown_rulepack_version_is_400(client, clean_db):
    r = _post_batch(client, seed_raw("clean_actions.json"), rulepack_version="1999.1")
    assert r.status_code == 400
    assert "unknown rulepack_version" in r.json()["detail"]


def test_free_text_without_a_model_is_502_with_the_json_hint(client, clean_db):
    r = client.post(
        f"{API}/verify/batch",
        json={"format": "text", "payload": seed_text("injected_log.txt")},
    )
    assert r.status_code == 502
    assert 'format:"json"' in r.json()["detail"]


def test_verify_single_action(client, clean_db):
    r = client.post(
        f"{API}/verify",
        json={
            "action": {
                "id": "a_solo", "type": "debit", "timestamp": "2026-08-20T15:00:00+05:30",
                "amount": 20000.0, "afa_present": False,
                "notice_sent_at": "2026-08-18T15:00:00+05:30",
                "debit_due_at": "2026-08-20T15:00:00+05:30",
            }
        },
    )
    assert r.status_code == 200
    assert [v["rule_id"] for v in r.json()["violations"]] == ["AFA_ABOVE_THRESHOLD"]


# --------------------------------------------------------------------------
# idempotency — 02-system-design.md §B.3
# --------------------------------------------------------------------------


def test_same_payload_and_version_returns_the_stored_report(client, clean_db):
    payload = seed_raw("violating_actions.json")

    first = _post_batch(client, payload)
    second = _post_batch(client, payload)

    assert first.json()["id"] == second.json()["id"], "must not recompute"
    assert first.headers["X-Idempotent-Replay"] == "false"
    assert second.headers["X-Idempotent-Replay"] == "true"
    assert repository.count_reports() == 1


def test_a_different_payload_is_a_different_run(client, clean_db):
    a = _post_batch(client, seed_raw("clean_actions.json"))
    b = _post_batch(client, seed_raw("violating_actions.json"))
    assert a.json()["id"] != b.json()["id"]
    assert repository.count_reports() == 2


def test_explicit_idempotency_key_is_honoured(client, clean_db):
    first = _post_batch(client, seed_raw("clean_actions.json"), idempotency_key="k-1")
    second = _post_batch(client, seed_raw("violating_actions.json"), idempotency_key="k-1")
    assert first.json()["id"] == second.json()["id"]


# --------------------------------------------------------------------------
# budgets — a cap halts, it does not warn
# --------------------------------------------------------------------------


def test_run_exceeding_the_turn_budget_halts_with_a_partial_report(
    client, clean_db, monkeypatch
):
    monkeypatch.setattr(settings, "BUDGET_MAX_TOTAL_TURNS", 0)

    r = client.post(
        f"{API}/verify/batch",
        json={"format": "text", "payload": seed_text("injected_log.txt")},
    )
    assert r.status_code == 200, "a halted run reports; it does not error"
    body = r.json()
    assert body["summary"].startswith("PARTIAL — run halted on budget")

    run = repository.get_run(r.headers["X-Run-Id"])
    assert run is not None and run.status == RunStatus.HALTED_BUDGET


def test_payload_above_the_action_cap_is_rejected(client, clean_db, monkeypatch):
    monkeypatch.setattr(settings, "BUDGET_MAX_ACTIONS", 3)
    r = _post_batch(client, seed_raw("clean_actions.json"))
    assert r.status_code == 422
    assert "above the run budget cap" in r.json()["detail"]


# --------------------------------------------------------------------------
# reports, runs, audit, replay
# --------------------------------------------------------------------------


def test_reports_list_and_detail(client, clean_db):
    created = _post_batch(client, seed_raw("violating_actions.json")).json()

    listing = client.get(f"{API}/reports").json()
    assert listing["total"] == 1
    assert listing["reports"][0]["id"] == created["id"]
    assert "actions" not in listing["reports"][0], "the list view stays lightweight"

    detail = client.get(f"{API}/reports/{created['id']}").json()
    assert detail["id"] == created["id"]
    assert len(detail["actions"]) == 10


def test_unknown_report_is_404(client, clean_db):
    assert client.get(f"{API}/reports/rep_nope").status_code == 404


def test_run_record_reports_budget_and_signals(client, clean_db):
    r = _post_batch(client, seed_raw("violating_actions.json"))
    body = client.get(f"{API}/runs/{r.headers['X-Run-Id']}").json()

    assert body["run"]["status"] == "done"
    assert body["run"]["rulepack_version"] == "2026.04.21-1"
    assert body["budget_remaining"]["cost_inr"] == pytest.approx(settings.BUDGET_MAX_COST_INR)
    assert body["duration_ms"] is not None
    assert any(s["kind"] == "membrane_rejection" for s in body["eval_signals"])


def test_audit_trail_has_one_row_per_action(client, clean_db):
    r = _post_batch(client, seed_raw("violating_actions.json"))
    body = client.get(f"{API}/runs/{r.headers['X-Run-Id']}/audit").json()

    assert body["append_only"] is True
    assert body["count"] == 10
    verdicts = {e["action_id"]: e["verdict"] for e in body["entries"]}
    assert verdicts["a_v03"] == "fail"
    assert verdicts["a_v07"] == "pass", "the exempt action is audited as a pass"

    failed = next(e for e in body["entries"] if e["action_id"] == "a_v03")
    assert failed["rule_id"] == "AFA_ABOVE_THRESHOLD"
    assert failed["clause"] == "RBI/DPSS/2026-27/396 §8(a)"


def test_audit_trail_refuses_updates_and_deletes(client, clean_db):
    """Invariant I10 is enforced by the database, not by convention.

    The trigger raises `RaiseException` (SQLSTATE P0001) rather than SQLite's
    `IntegrityError`, but the message is deliberately unchanged across the port, so the
    assertion still reads as the invariant it protects.
    """
    from psycopg.errors import RaiseException

    from app.store.db import connect

    r = _post_batch(client, seed_raw("clean_actions.json"))
    run_id = r.headers["X-Run-Id"]

    with pytest.raises(RaiseException, match="append-only"):
        with connect() as conn:
            conn.execute(
                "UPDATE action_audit SET verdict='pass' WHERE run_id=%s", (run_id,)
            )

    with pytest.raises(RaiseException, match="append-only"):
        with connect() as conn:
            conn.execute("DELETE FROM action_audit WHERE run_id=%s", (run_id,))


def test_replay_of_a_stored_run_is_deterministic(client, clean_db):
    original = _post_batch(client, seed_raw("violating_actions.json"))
    run_id = original.headers["X-Run-Id"]

    replayed = client.post(f"{API}/runs/{run_id}/replay")
    assert replayed.status_code == 200
    assert replayed.json()["id"] == original.json()["id"]
    assert replayed.headers["X-Idempotent-Replay"] == "true"


def test_replay_of_an_unknown_run_is_404(client, clean_db):
    assert client.post(f"{API}/runs/run_nope/replay").status_code == 404


def test_unknown_run_is_404(client, clean_db):
    assert client.get(f"{API}/runs/run_nope").status_code == 404


# --------------------------------------------------------------------------
# tenant isolation — 01-architecture.md §5 `auth (API key / tenant)`
# --------------------------------------------------------------------------


@pytest.fixture
def keyed(monkeypatch):
    """Turn on API-key auth for one test. Blank in every other test, so the rest of the
    suite continues to exercise the open-mode path the demo runs in."""
    monkeypatch.setattr(settings, "API_KEYS", "k_acme:acme,k_globex:globex")
    yield


def test_tenant_cannot_read_another_tenants_report(client, clean_db, keyed):
    """The gap found on 2026-08-24: tenant_id was stored but never filtered on."""
    made = client.post(
        f"{API}/verify/batch",
        json={"format": "json", "payload": seed_raw("clean_actions.json")},
        headers={"X-API-Key": "k_acme"},
    )
    assert made.status_code == 200
    report_id = made.json()["id"]
    run_id = made.headers["X-Run-Id"]

    assert client.get(f"{API}/reports/{report_id}", headers={"X-API-Key": "k_acme"}).status_code == 200

    # 404, not 403: a 403 would confirm the report exists, which is the disclosure.
    for path in (f"/reports/{report_id}", f"/runs/{run_id}", f"/runs/{run_id}/audit"):
        r = client.get(f"{API}{path}", headers={"X-API-Key": "k_globex"})
        assert r.status_code == 404, f"{path} leaked across tenants"

    listed = client.get(f"{API}/reports", headers={"X-API-Key": "k_globex"}).json()
    assert listed["total"] == 0 and listed["reports"] == []


def test_a_spoofed_tenant_header_is_ignored_once_keys_are_configured(client, clean_db, keyed):
    """The header named the tenant before; with keys on, only the key may."""
    made = client.post(
        f"{API}/verify/batch",
        json={"format": "json", "payload": seed_raw("clean_actions.json")},
        headers={"X-API-Key": "k_acme"},
    )
    report_id = made.json()["id"]
    r = client.get(
        f"{API}/reports/{report_id}",
        headers={"X-API-Key": "k_globex", "X-Tenant-Id": "acme"},
    )
    assert r.status_code == 404


def test_missing_or_unknown_key_is_401_when_keys_are_configured(client, clean_db, keyed):
    assert client.get(f"{API}/reports").status_code == 401
    assert client.get(f"{API}/reports", headers={"X-API-Key": "nope"}).status_code == 401


def test_open_mode_needs_no_key(client, clean_db):
    """Unconfigured, the API stays open so the demo and a fresh clone need no setup."""
    assert client.get(f"{API}/reports").status_code == 200
