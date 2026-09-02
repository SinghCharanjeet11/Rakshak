"""Tenant resolution at the gateway — `01-architecture.md` §5 `auth (API key / tenant)`.

This closes a gap found on 2026-08-24 and fixed on 2026-09-02: `tenant_id` was threaded
all the way from the request header through `Run` to a column on `runs`, but **nothing
read it back**. Every repository query returned any row to any caller, so the tenant
boundary was decorative and any caller could read another tenant's compliance reports and
audit trail by guessing an id.

Two decisions worth stating:

* **404, not 403, on a cross-tenant read.** A 403 confirms the report exists, which is
  itself a disclosure — "does Globex have a report with this id" is exactly the question a
  competitor would like answered. The route cannot distinguish "absent" from "not yours",
  and that is deliberate.
* **It degrades to open.** With no keys configured the API behaves exactly as before, so
  the demo, the E2E suite and a fresh clone need no setup. Configure `API_KEYS` and the
  header stops being trusted: the key alone names the tenant.
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.config import settings


def resolve_tenant(
    x_api_key: str | None = Header(default=None),
    x_tenant_id: str = Header(default="default"),
) -> str:
    """The tenant this request may see. Raises 401 when a key is required and wrong."""
    keys = settings.api_key_map
    if not keys:
        # Open mode — single-tenant demo. The header is advisory, as it always was.
        return x_tenant_id
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="X-API-Key required")
    tenant = keys.get(x_api_key)
    if tenant is None:
        raise HTTPException(status_code=401, detail="unknown API key")
    return tenant
