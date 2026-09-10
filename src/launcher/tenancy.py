"""Tenant enforcement for multi-user use (#5, ADR-0004).

Identity: Bearer tokens bound to one Worker user. Only sha256 hashes
touch the database; plaintext shows once at issue time. Zero token rows
means single-operator open mode (every prior test and CLI keeps working);
the first issued token switches enforcement on.

Ownership: a project belongs to the tenant that bound it via /voices
(project equals voice, ADR-0001). Drafts inherit ownership through their
project_id. Cross-tenant resource access raises 404 (never confirm a
foreign project exists, same as the Worker's relayOwnedBy); acting under
someone else's worker_user_id raises 403; missing/invalid credentials
raise 401.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from launcher.models import Draft, TenantToken, VoiceBinding

TenantId = str | None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def enforcement_enabled(session: Session) -> bool:
    return session.query(TenantToken).count() > 0


def issue_token(session: Session, worker_user_id: str) -> str:
    """Mint one bearer token for a tenant; returns plaintext exactly once."""
    if not worker_user_id.strip():
        raise ValueError("worker_user_id is required")
    token = secrets.token_urlsafe(32)
    session.add(
        TenantToken(worker_user_id=worker_user_id, token_hash=hash_token(token))
    )
    session.flush()
    return token


def tenant_projects(session: Session, tenant: str) -> set[str]:
    return {
        row.project_id
        for row in session.query(VoiceBinding)
        .filter_by(worker_user_id=tenant)
        .all()
    }


def resolve_tenant(session: Session, authorization: str | None) -> TenantId:
    """Map an Authorization header to a tenant, or None in open mode."""
    if not enforcement_enabled(session):
        return None
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    row = (
        session.query(TenantToken).filter_by(token_hash=hash_token(token)).one_or_none()
        if token
        else None
    )
    if row is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return row.worker_user_id


def require_project(session: Session, tenant: TenantId, project_id: str | None) -> None:
    """404 unless the project belongs to the tenant (no-op in open mode)."""
    if tenant is None:
        return
    if not project_id or project_id not in tenant_projects(session, tenant):
        raise HTTPException(status_code=404, detail="project not found")


def require_draft(session: Session, tenant: TenantId, draft_id: int) -> Draft:
    """Load a draft the tenant may see, else 404 (no-op owner in open mode)."""
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    require_project(session, tenant, draft.project_id)
    return draft


def require_owner(tenant: TenantId, worker_user_id: str) -> None:
    """403 when an authenticated tenant acts as someone else (no-op in open mode)."""
    if tenant is not None and worker_user_id != tenant:
        raise HTTPException(status_code=403, detail="worker user mismatch")


def tenant_dep(get_tenant: Callable[[], TenantId] | None) -> Callable[[], TenantId]:
    """Shared Depends target for routers: the app tenant resolver, or an
    open-mode stub when routers are used without one (unit tests)."""
    if get_tenant is not None:
        return get_tenant

    def _open_mode() -> TenantId:
        return None

    return _open_mode
