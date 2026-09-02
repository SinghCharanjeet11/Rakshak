"""Run, Budget, RunStatus — the harness model (02-system-design.md §B.1).

Budgets are product features, not billing alerts: a run that *would* exceed a cap is
halted and reported (`HALTED_BUDGET`) with a partial report, never silently continued.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class RunStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    HALTED_BUDGET = "halted_budget"
    FAILED = "failed"


class Budget(BaseModel):
    max_turns: int = 25  # per subagent (SDK default ceiling)
    max_total_turns: int = 60  # whole run
    max_tokens: int = 40_000
    max_cost_inr: float = 5.0  # hard cap per run
    max_actions: int = 500


class Run(BaseModel):
    id: str
    tenant_id: str
    correlation_id: str
    rulepack_version: str
    idempotency_key: Optional[str] = None
    status: RunStatus = RunStatus.RUNNING
    budget: Budget = Budget()
    tokens_used: int = 0
    cost_inr: float = 0.0
    turns_used: int = 0
    started_at: datetime
    ended_at: Optional[datetime] = None


class BudgetExceeded(Exception):
    """Raised by the orchestrator's pre-turn guard. Ends the run as HALTED_BUDGET."""

    def __init__(self, cap: str, limit: float, attempted: float):
        self.cap = cap
        self.limit = limit
        self.attempted = attempted
        super().__init__(f"budget cap '{cap}' exceeded: {attempted} > {limit}")
