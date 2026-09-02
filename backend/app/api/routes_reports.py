from fastapi import APIRouter, Depends, HTTPException, Query

from app.api._auth import resolve_tenant
from app.core.models import Report
from app.store import repository

router = APIRouter(tags=["reports"])


@router.get("/reports")
def list_reports(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant_id: str = Depends(resolve_tenant),
) -> dict[str, object]:
    reports = repository.list_reports(limit=limit, offset=offset, tenant_id=tenant_id)
    return {
        "total": repository.count_reports(tenant_id=tenant_id),
        "limit": limit,
        "offset": offset,
        # The list view needs headline numbers, not full action arrays.
        "reports": [
            {
                "id": r.id,
                "created_at": r.created_at,
                "rulepack_version": r.rulepack_version,
                "score": r.score,
                "passed": r.passed,
                "failed": r.failed,
                "summary": r.summary,
            }
            for r in reports
        ],
    }


@router.get("/reports/{report_id}", response_model=Report)
def get_report(report_id: str, tenant_id: str = Depends(resolve_tenant)) -> Report:
    report = repository.get_report(report_id, tenant_id=tenant_id)
    if report is None:
        # 404 rather than 403 on a cross-tenant read: a 403 would confirm the report
        # exists, which is itself the disclosure. See api/_auth.py.
        raise HTTPException(status_code=404, detail=f"no report {report_id}")
    return report
