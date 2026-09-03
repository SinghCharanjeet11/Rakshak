from datetime import date

from fastapi import APIRouter

from app.config import settings
from app.orchestration.orchestrator import get_pack

router = APIRouter(tags=["health"])

# A currency check older than this is treated as no longer meaningful. Matches
# STALE_AFTER_DAYS in scripts/check_circulars.py.
CIRCULAR_STALE_AFTER_DAYS = 90


@router.get("/health")
def health() -> dict[str, object]:
    pack = get_pack()
    unverified = pack.unverified_values()

    # A pack can go wrong without any of its own text changing: the circular it cites may
    # be amended or repealed. RBI/DPSS/2026-27/396 repealed eight circulars at once, so
    # this is a real failure mode, and one nothing else in the system would notice.
    checked_on = next(
        (s.circular_checked_on for s in pack.sources if s.primary and s.circular_checked_on),
        None,
    )
    days_since = (date.today() - checked_on).days if checked_on else None

    return {
        "status": "ok",
        "rulepack": pack.version,
        "rules_loaded": len(pack.rules),
        "exemptions_loaded": len(pack.exemptions),
        "llm_enabled": settings.llm_enabled,
        # Surfaced deliberately: OPEN-2 says an unconfirmed regulatory value is the top
        # project risk, so it should be visible on the liveness probe, not buried.
        "unverified_rule_values": unverified,
        "circular_checked_on": checked_on.isoformat() if checked_on else None,
        "circular_check_age_days": days_since,
        "circular_check_stale": (
            True if days_since is None else days_since > CIRCULAR_STALE_AFTER_DAYS
        ),
    }
