"""Request dependencies: database session, signed-in user, permission checks."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import Settings
from ..core.permissions import Permission, permissions_for
from ..core.security import hash_token
from ..db.database import Database, as_utc
from ..db.models import AuditLog, AuthSession, BoardMembership, User

SESSION_COOKIE = "samspace_session"
CSRF_HEADER = "x-sam-request"


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_database(request: Request) -> Database:
    return request.app.state.db


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.db.session()
    try:
        yield session
    finally:
        session.close()


@dataclass
class CurrentUser:
    user: User
    membership: BoardMembership
    session_id: int

    @property
    def role(self) -> str:
        return self.membership.role

    @property
    def organization_id(self) -> int:
        return self.membership.organization_id

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_for(self.membership.role)


def current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    now = datetime.now(timezone.utc)
    if session is None or session.revoked_at is not None or as_utc(session.expires_at) <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again.")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    membership = db.scalar(select(BoardMembership).where(BoardMembership.user_id == user.id).limit(1))
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account is not on a board yet.")
    return CurrentUser(user=user, membership=membership, session_id=session.id)


def require(permission: Permission):
    def dependency(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> CurrentUser:
        if permission not in cu.permissions:
            audit(db, cu, "access_denied", permission.value)
            from ..db.models import SecurityEvent
            db.add(SecurityEvent(organization_id=cu.organization_id, user_id=cu.user.id, category="permission_denied", severity="low",
                                 defense="Server-side role permissions",
                                 detail=f"A {cu.role} was refused an action that needs “{permission.value}”."))
            db.commit()
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Your board role ({cu.role}) does not have access to this area.",
            )
        return cu

    return dependency


def audit(db: Session, cu: CurrentUser | None, action: str, target: str = "", **detail) -> None:
    db.add(
        AuditLog(
            organization_id=cu.organization_id if cu else None,
            user_id=cu.user.id if cu else None,
            action=action,
            target=target,
            detail=detail or None,
        )
    )


def is_foreign_or_missing(db: Session, cu: CurrentUser, row, label: str) -> bool:
    """True if the record does not exist or belongs to another workspace. A cross-workspace attempt is recorded
    as a security event; both cases look identical to the caller (404), so nothing about the other workspace leaks."""
    if row is None:
        return True
    if getattr(row, "organization_id", cu.organization_id) != cu.organization_id:
        from ..db.models import SecurityEvent
        db.add(SecurityEvent(organization_id=cu.organization_id, user_id=cu.user.id, category="cross_workspace", severity="high",
                             defense="Workspace-scoped queries", detail=f"Blocked access to {label} #{getattr(row, 'id', '?')}, which belongs "
                             "to another workspace."))
        db.commit()
        return True
    return False


def security_event(db: Session, cu: CurrentUser | None, category: str, detail: str, *, severity: str = "medium",
                   defense: str = "", commit: bool = True) -> None:
    """Record a security event from a route (upload rejected, URL blocked, ...) on the request's own session, so it
    never waits on a second connection. Details are redacted."""
    from ..db.models import SecurityEvent
    from ..safety.redact import configured_secrets, redact
    db.add(SecurityEvent(organization_id=cu.organization_id if cu else None, user_id=cu.user.id if cu else None, category=category,
                         severity=severity, defense=defense[:80], detail=redact(detail, configured_secrets())[:1000]))
    if commit:
        db.commit()
