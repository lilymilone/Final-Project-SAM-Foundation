"""Sign in, sign out, and who am I. Sessions live on the server; the browser
holds only an HttpOnly, SameSite=Strict cookie."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.config import Settings
from ...core.security import hash_password, hash_token, new_session_token, verify_password
from ...db.models import AuthSession, BoardMembership, Organization, User
from ...db.seed import DEMO_PASSWORD_DEFAULT, demo_password
from ..deps import SESSION_COOKIE, CurrentUser, audit, current_user, get_db, get_settings_dep

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Compared against when the email is unknown, so failed logins take the same time.
_DUMMY_HASH = hash_password("not-a-real-password")


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


def user_payload(cu: CurrentUser, db: Session) -> dict:
    org = db.get(Organization, cu.organization_id)
    u = cu.user
    return {
        "id": u.id,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "email": u.email,
        "is_demo": u.is_demo,
        "role": cu.role,
        "title": cu.membership.title,
        "permissions": sorted(p.value for p in cu.permissions),
        "organization": {"id": org.id, "name": org.name, "is_demo": org.is_demo} if org else None,
        "settings": {"animations_enabled": u.animations_enabled, "model_strategy": u.model_strategy},
    }


@router.post("/login")
def login(
    body: LoginBody,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> dict:
    limiter = request.app.state.login_limiter
    email = body.email.strip().lower()
    if limiter.blocked(email):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Please wait 15 minutes.")

    user = db.scalar(select(User).where(User.email == email))
    valid = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not user.is_active or not valid:
        limiter.fail(email)
        audit(db, None, "login_failed", email)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That email and password don't match our records.")
    limiter.reset(email)

    membership = db.scalar(select(BoardMembership).where(BoardMembership.user_id == user.id).limit(1))
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account is not on a board yet.")

    now = datetime.now(timezone.utc)
    token = new_session_token()
    expires = now + timedelta(hours=settings.session_hours)
    session = AuthSession(user_id=user.id, token_hash=hash_token(token), expires_at=expires)
    user.last_login_at = now
    db.add(session)
    db.flush()
    cu = CurrentUser(user=user, membership=membership, session_id=session.id)
    audit(db, cu, "login", email)
    db.commit()

    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(settings.session_hours * 3600),
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        path="/",
    )
    return {"user": user_payload(cu, db), "expires_at": expires.isoformat()}


@router.post("/logout")
def logout(response: Response, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    session = db.get(AuthSession, cu.session_id)
    if session is not None:
        session.revoked_at = datetime.now(timezone.utc)
    audit(db, cu, "logout")
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return {"user": user_payload(cu, db)}


@router.get("/session")
def session_check(request: Request, db: Session = Depends(get_db)) -> dict:
    """Startup check for the web app: {"user": ...} if signed in, else {"user": null}.
    Same validation as every protected route, but a signed-out visitor is not an error."""
    try:
        cu = current_user(request, db)
    except HTTPException:
        return {"user": None}
    return {"user": user_payload(cu, db)}


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> dict:
    """Lists the synthetic demo logins for the sign-in page. It never returns a
    password, only whether the documented default (see README) is in use."""
    if not settings.demo_mode:
        return {"demo_mode": False, "accounts": [], "default_password": False}
    rows = db.execute(
        select(User.email, User.first_name, BoardMembership.role, BoardMembership.title)
        .join(BoardMembership, BoardMembership.user_id == User.id)
        .where(User.is_demo.is_(True), User.is_active.is_(True))
        .order_by(User.id)
    ).all()
    return {
        "demo_mode": True,
        "accounts": [{"email": r.email, "first_name": r.first_name, "role": r.role, "title": r.title} for r in rows],
        "default_password": demo_password() == DEMO_PASSWORD_DEFAULT,
    }
