"""Core Pydantic models — 02-system-design.md §A.1.

This module is part of the deterministic core. It must not import from `app.llm`,
`app.orchestration`, `app.store`, or any network library. See `tests/test_isolation.py`.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ActionType(str, Enum):
    MANDATE_RETRY = "mandate_retry"
    DEBIT = "debit"
    NOTIFY = "notify"
    CONTACT = "contact"
    ESCALATE = "escalate"


class Channel(str, Enum):
    SMS = "sms"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    CALL = "call"
    PUSH = "push"


class MandateCategory(str, Enum):
    """The three categories §8(b) of the 2026 framework treats differently.

    Closed, like `ActionType` and `Channel`: a category the circular does not name is a
    membrane rejection rather than a silently-ignored value, because an invented category
    is exactly how an AFA requirement would get wrongly waived.
    """

    INSURANCE_PREMIUM = "insurance_premium"
    MUTUAL_FUND_SUBSCRIPTION = "mutual_fund_subscription"
    CREDIT_CARD_BILL = "credit_card_bill"


class Action(BaseModel):
    """One proposed action emitted by a payment-recovery agent.

    Every field beyond `id`/`type`/`timestamp` is optional: a real agent log is sparse,
    and a *missing* field is itself evidence (a debit with no `notice_sent_at` fails
    PRE_DEBIT_NOTICE_24H precisely because the notice cannot be shown to exist).

    `extra="forbid"` is load-bearing, not tidiness. The validation membrane (invariant
    I3) promises that a hallucinated field is *rejected*; with Pydantic's default
    `extra="ignore"` an invented key would be silently dropped and the action would sail
    through as valid. Forbidding extras is what makes the membrane's guarantee real.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    type: ActionType
    mandate_id: Optional[str] = None
    customer_id: Optional[str] = None
    amount: Optional[float] = None  # INR
    currency: str = "INR"
    timestamp: datetime
    retry_index: Optional[int] = None
    window_start: Optional[datetime] = None
    notice_sent_at: Optional[datetime] = None
    debit_due_at: Optional[datetime] = None
    afa_present: Optional[bool] = None
    mcc: Optional[str] = None
    category: Optional[MandateCategory] = None
    channel: Optional[Channel] = None
    dispute_active: Optional[bool] = None
    consent_opted_out: Optional[bool] = None
    # Deliberately NOT the same field as `consent_opted_out`. §6(c) of the 2026 framework
    # grants an opt-out from "any particular transaction or the e-mandate" — a debit
    # instruction — whereas `consent_opted_out` records an outreach/DND preference. Sharing
    # one field would fail a lawful debit for a customer who merely opted out of marketing
    # SMS, which is the false-positive class §8(b) already caught us on once.
    mandate_opted_out: Optional[bool] = None


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Violation(BaseModel):
    action_id: str
    rule_id: str
    title: str
    severity: Severity
    offending_value: str
    clause: str
    source: str
    explanation: Optional[str] = None  # LLM-filled, display-only (invariant I8)


class ExemptionApplied(BaseModel):
    """A rule that was suppressed for an action by an exemption.

    Additive to the Report shape in 02-system-design.md §A.1: the report is otherwise
    unable to distinguish "passed because compliant" from "passed because exempt", and
    04-frontend.md §3 requires the FASTag row to read as *exempt*, not merely clean.
    """

    action_id: str
    rule_id: str
    exemption_id: str
    reason: str
    clause: str
    source: str


class Report(BaseModel):
    id: str
    created_at: datetime
    rulepack_version: str
    actions: list[Action] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    exemptions_applied: list[ExemptionApplied] = Field(default_factory=list)
    score: float
    passed: int
    failed: int
    summary: str
    correlation_id: Optional[str] = None
    # Additive: the report page reaches its run's budget, eval signals and audit trail
    # through this. Without it a stored report is a dead end — you can see the verdicts
    # but not the evidence of how they were produced.
    run_id: Optional[str] = None
