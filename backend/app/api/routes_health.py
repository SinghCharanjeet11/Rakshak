from fastapi import APIRouter

from app.config import settings
from app.orchestration.orchestrator import get_pack

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, object]:
    pack = get_pack()
    unverified = pack.unverified_values()
    return {
        "status": "ok",
        "rulepack": pack.version,
        "rules_loaded": len(pack.rules),
        "exemptions_loaded": len(pack.exemptions),
        "llm_enabled": settings.llm_enabled,
        # Surfaced deliberately: OPEN-2 says an unconfirmed regulatory value is the top
        # project risk, so it should be visible on the liveness probe, not buried.
        "unverified_rule_values": unverified,
    }
