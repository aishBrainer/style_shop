"""Authentication endpoints (§7, §56)."""

from __future__ import annotations

import secrets
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import ACCESS_COOKIE, REFRESH_COOKIE, CurrentUser, DbSession, client_ip
from app.core.errors import ConflictError, UnauthorizedError, ValidationError
from app.core.logging import get_logger
from app.core.ratelimit import auth_rate_limit
from app.models import Membership, Organization
from app.schemas.auth import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    EmailVerifyRequest,
    LoginRequest,
    MembershipOut,
    OrganizationOut,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    SessionOut,
    UpdateProfileRequest,
    UserOut,
)
from app.schemas.common import Message
from app.services import audit, auth_service, email

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ------------------------------------------------------------------ cookies --

def _set_session_cookies(response: Response, access: str, refresh: str) -> None:
    """httpOnly so no script can read them; SameSite=lax so a cross-site POST
    cannot ride along (§58)."""
    common = {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "path": "/",
    }
    if settings.cookie_domain:
        common["domain"] = settings.cookie_domain

    response.set_cookie(
        ACCESS_COOKIE, access, max_age=settings.access_token_ttl_minutes * 60, **common
    )
    response.set_cookie(
        REFRESH_COOKIE, refresh, max_age=settings.refresh_token_ttl_days * 86400, **common
    )


def _clear_session_cookies(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(
            name, path="/", domain=settings.cookie_domain or None
        )


async def _session_payload(session, user) -> SessionOut:
    memberships = (
        await session.scalars(select(Membership).where(Membership.user_id == user.id))
    ).all()

    org = None
    if user.default_organization_id:
        org = await session.get(Organization, user.default_organization_id)
    if org is None and memberships:
        org = await session.get(Organization, memberships[0].organization_id)
    if org is None:
        raise UnauthorizedError("Your account is not attached to a workspace.")

    out_memberships = []
    for m in memberships:
        m_org = await session.get(Organization, m.organization_id)
        out = MembershipOut.model_validate(m)
        out.organization = OrganizationOut.model_validate(m_org) if m_org else None
        out_memberships.append(out)

    return SessionOut(
        user=UserOut.model_validate(user),
        organization=OrganizationOut.model_validate(org),
        memberships=out_memberships,
    )


# ------------------------------------------------------------------- routes --

@router.post("/register", response_model=SessionOut, status_code=201,
             dependencies=[Depends(auth_rate_limit)])
async def register(
    payload: RegisterRequest, request: Request, response: Response, session: DbSession
) -> SessionOut:
    user, _org = await auth_service.register(
        session,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )
    access, refresh = await auth_service.issue_tokens(
        session,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
    )
    _set_session_cookies(response, access, refresh)

    await email.send_verification(user.email, auth_service.make_email_verify_token(user))
    await audit.record(session, action="auth.register", actor=user, request=request)

    return await _session_payload(session, user)


@router.post("/login", response_model=SessionOut, dependencies=[Depends(auth_rate_limit)])
async def login(
    payload: LoginRequest, request: Request, response: Response, session: DbSession
) -> SessionOut:
    user = await auth_service.authenticate(
        session, email=payload.email, password=payload.password
    )
    access, refresh = await auth_service.issue_tokens(
        session,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
    )
    _set_session_cookies(response, access, refresh)
    await audit.record(session, action="auth.login", actor=user, request=request)
    return await _session_payload(session, user)


@router.post("/refresh", response_model=SessionOut)
async def refresh(
    request: Request,
    response: Response,
    session: DbSession,
    afs_refresh: Annotated[str | None, Cookie()] = None,
) -> SessionOut:
    if not afs_refresh:
        raise UnauthorizedError("No active session.")

    user, access, new_refresh = await auth_service.rotate_refresh_token(
        session,
        afs_refresh,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
    )
    _set_session_cookies(response, access, new_refresh)
    return await _session_payload(session, user)


@router.post("/logout", response_model=Message)
async def logout(
    response: Response,
    session: DbSession,
    afs_refresh: Annotated[str | None, Cookie()] = None,
) -> Message:
    if afs_refresh:
        await auth_service.revoke_refresh_token(session, afs_refresh)
    _clear_session_cookies(response)
    return Message(message="Signed out.")


@router.get("/session", response_model=SessionOut)
async def current_session(session: DbSession, user: CurrentUser) -> SessionOut:
    return await _session_payload(session, user)


@router.patch("/profile", response_model=UserOut)
async def update_profile(
    payload: UpdateProfileRequest, session: DbSession, user: CurrentUser
) -> UserOut:
    if payload.full_name is not None:
        user.full_name = payload.full_name
    await session.flush()
    return UserOut.model_validate(user)


# ------------------------------------------------------- email verification --

@router.post("/verify-email/request", response_model=Message,
             dependencies=[Depends(auth_rate_limit)])
async def request_verification(session: DbSession, user: CurrentUser) -> Message:
    if user.is_verified:
        return Message(message="Your email is already verified.")
    await email.send_verification(user.email, auth_service.make_email_verify_token(user))
    return Message(message="Verification email sent.")


@router.post("/verify-email/confirm", response_model=Message)
async def confirm_verification(payload: EmailVerifyRequest, session: DbSession) -> Message:
    await auth_service.confirm_email(session, payload.token)
    return Message(message="Email verified.")


# ------------------------------------------------------------ password flow --

@router.post("/password/forgot", response_model=Message,
             dependencies=[Depends(auth_rate_limit)])
async def forgot_password(payload: PasswordResetRequest, session: DbSession) -> Message:
    from app.models import User

    user = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if user is not None and user.hashed_password and user.deleted_at is None:
        await email.send_password_reset(
            user.email, auth_service.make_password_reset_token(user)
        )

    # Always the same response: revealing which addresses exist is an
    # enumeration oracle.
    return Message(message="If that email is registered, a reset link is on its way.")


@router.post("/password/reset", response_model=Message,
             dependencies=[Depends(auth_rate_limit)])
async def reset_password(payload: PasswordResetConfirm, session: DbSession) -> Message:
    await auth_service.reset_password(session, payload.token, payload.password)
    return Message(message="Password updated. Please sign in.")


@router.post("/password/change", response_model=Message)
async def change_password(
    payload: ChangePasswordRequest, response: Response, session: DbSession, user: CurrentUser
) -> Message:
    await auth_service.change_password(
        session, user, payload.current_password, payload.new_password
    )
    _clear_session_cookies(response)
    return Message(message="Password updated. Please sign in again.")


# ---------------------------------------------------------------- deletion ---

@router.post("/delete-account", response_model=Message)
async def delete_account(
    payload: DeleteAccountRequest,
    request: Request,
    response: Response,
    session: DbSession,
    user: CurrentUser,
) -> Message:
    from app.core.security import verify_password

    # Password accounts must re-authenticate; OAuth accounts have no password
    # to check, and the session cookie is the proof of identity.
    if user.hashed_password:
        if not payload.password or not verify_password(payload.password, user.hashed_password):
            raise UnauthorizedError("Your password is incorrect.")

    await audit.record(session, action="auth.delete_account", actor=user, request=request)
    await auth_service.delete_account(session, user)
    _clear_session_cookies(response)
    return Message(message="Your account has been deleted.")


# ------------------------------------------------------------ Google OAuth ---

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
OAUTH_STATE_COOKIE = "afs_oauth_state"


@router.get("/google/start")
async def google_start(response: Response) -> RedirectResponse:
    if not settings.google_client_id:
        raise ValidationError("Google sign-in is not configured on this server.")

    # CSRF defence: the state we plant in a cookie must come back unchanged.
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    redirect = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")
    redirect.set_cookie(
        OAUTH_STATE_COOKIE, state,
        max_age=600, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/",
    )
    return redirect


@router.get("/google/callback")
async def google_callback(
    request: Request,
    session: DbSession,
    code: str | None = None,
    state: str | None = None,
    afs_oauth_state: Annotated[str | None, Cookie()] = None,
) -> RedirectResponse:
    if not code or not state or not afs_oauth_state:
        return RedirectResponse(f"{settings.web_url}/login?error=oauth_failed")
    if not secrets.compare_digest(state, afs_oauth_state):
        log.warning("auth.oauth_state_mismatch")
        return RedirectResponse(f"{settings.web_url}/login?error=oauth_state")

    async with httpx.AsyncClient(timeout=10) as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_response.status_code != 200:
            log.warning("auth.oauth_token_exchange_failed", status=token_response.status_code)
            return RedirectResponse(f"{settings.web_url}/login?error=oauth_failed")

        access_token = token_response.json().get("access_token")
        profile_response = await client.get(
            GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        if profile_response.status_code != 200:
            return RedirectResponse(f"{settings.web_url}/login?error=oauth_failed")
        profile = profile_response.json()

    if not profile.get("email_verified", False):
        return RedirectResponse(f"{settings.web_url}/login?error=email_unverified")

    user, _ = await auth_service.authenticate_google(
        session,
        google_sub=profile["sub"],
        email=profile["email"],
        name=profile.get("name"),
        picture=profile.get("picture"),
    )
    access, refresh = await auth_service.issue_tokens(
        session,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
    )

    redirect = RedirectResponse(f"{settings.web_url}/dashboard")
    _set_session_cookies(redirect, access, refresh)
    redirect.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    return redirect
