"""Authentication endpoints (scope M1 FE-1/2/3)."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field

from sendox_api import email as mail
from sendox_api import tasks
from sendox_api.config import Settings
from sendox_api.db import global_session, user_session
from sendox_api.dependencies import CurrentUser, SettingsDep
from sendox_api.models import Tenant, User
from sendox_api.security import (
    ACCESS_TOKEN_TTL,
    MIN_PASSWORD_LENGTH,
    TokenPurpose,
    create_access_token,
)
from sendox_api.services import auth, workspaces
from sendox_api.services.errors import (
    AccountInactive,
    EmailAlreadyRegistered,
    EmailNotVerified,
    InvalidCredentials,
    TokenNotUsable,
    WeakPassword,
)

router = APIRouter(prefix="/auth", tags=["auth"])

Password = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: Password
    full_name: str | None = Field(default=None, max_length=200)
    workspace_name: str | None = Field(
        default=None, max_length=200, description="Creates a first workspace if given"
    )


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenRequest(BaseModel):
    token: str = Field(min_length=10)


class ResetRequest(BaseModel):
    token: str = Field(min_length=10)
    password: Password


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: Password


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str | None
    email_verified: bool
    created_at: datetime


class WorkspaceOut(BaseModel):
    id: str
    name: str
    slug: str
    timezone: str
    role: str


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        email_verified=user.email_verified_at is not None,
        created_at=user.created_at,
    )


def _dev_token(settings: Settings, token: str) -> str | None:
    """Expose a one-time token in the response — development only.

    Mailpit is part of the Docker stack, so on the no-Docker path there is nowhere
    to read a verification link from. Returning the token when ENV is not
    production makes the whole signup flow testable with no mail server at all.
    Gated hard: in production this is always None, and a test asserts that.
    """
    return None if settings.is_production else token


def _set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=int(ACCESS_TOKEN_TTL.total_seconds()),
        # Not readable by page scripts, so an XSS bug cannot steal the session.
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, summary="Create an account")
async def register(request: RegisterRequest, settings: SettingsDep) -> dict[str, Any]:
    """Creates an unverified account and emails a confirmation link.

    The account cannot sign in until the link is followed, which proves the address
    belongs to the person and keeps the sending domain's reputation intact.
    """
    try:
        with global_session(settings) as session:
            user, token = auth.register(session, request.email, request.password, request.full_name)
            if request.workspace_name:
                workspaces.create_workspace(session, user, request.workspace_name)
            session.flush()
            payload = _user_out(user)
            address = user.email
    except EmailAlreadyRegistered as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="that email address is already registered"
        ) from exc
    except WeakPassword as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.problems) from exc

    tasks.queue_email(mail.verification_email(settings, address, token))

    return {
        "user": payload,
        "next": "Check your inbox for a confirmation link.",
        "dev_hint": None
        if settings.is_production
        else "Mailpit (Docker stack) shows the email at http://localhost:8025.",
        "dev_verification_token": _dev_token(settings, token),
    }


@router.post("/verify-email", summary="Confirm an email address")
async def verify_email(
    request: TokenRequest, response: Response, settings: SettingsDep
) -> dict[str, Any]:
    """Confirms the address and signs the user in, so there is no second step."""
    try:
        with global_session(settings) as session:
            user = auth.verify_email(session, request.token)
            session.flush()
            payload = _user_out(user)
            token, _ = create_access_token(settings, user.id)
    except TokenNotUsable as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _set_session_cookie(response, settings, token)
    return {"user": payload, "access_token": token, "token_type": "bearer"}


@router.post("/resend-verification", summary="Send a fresh confirmation link")
async def resend_verification(request: LoginRequest, settings: SettingsDep) -> dict[str, Any]:
    """Deliberately indistinguishable for unknown addresses and wrong passwords."""
    with global_session(settings) as session:
        user = auth.find_by_email(session, request.email)
        token: str | None = None
        if user is not None and user.email_verified_at is None:
            token = auth.issue_email_token(session, user, TokenPurpose.VERIFY_EMAIL)
            session.flush()
            address = user.email

    if token:
        tasks.queue_email(mail.verification_email(settings, address, token))

    return {
        "status": "If that account needs confirming, a new link is on its way.",
        "dev_verification_token": _dev_token(settings, token) if token else None,
    }


@router.post("/login", summary="Sign in")
async def login(request: LoginRequest, response: Response, settings: SettingsDep) -> dict[str, Any]:
    try:
        with global_session(settings) as session:
            user = auth.authenticate(session, request.email, request.password)
            payload = _user_out(user)
            token, expires_at = create_access_token(settings, user.id)
    except InvalidCredentials as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except EmailNotVerified as exc:
        # 403, not 401: the credentials were right, the account is not ready.
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AccountInactive as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    _set_session_cookie(response, settings, token)
    return {
        "user": payload,
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
    }


@router.post("/logout", summary="Sign out")
async def logout(response: Response, settings: SettingsDep) -> dict[str, str]:
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"status": "signed out"}


@router.get("/me", summary="The signed-in user and their workspaces")
async def me(user: CurrentUser, settings: SettingsDep) -> dict[str, Any]:
    with user_session(settings, user.id) as session:
        memberships = workspaces.memberships_for_user(session, user.id)
        pairs = [(m.tenant_id, m.role) for m in memberships]

    with global_session(settings) as session:
        workspace_list = []
        for tenant_id, role in pairs:
            tenant = session.get(Tenant, tenant_id)
            if tenant is not None:
                workspace_list.append(
                    WorkspaceOut(
                        id=str(tenant.id),
                        name=tenant.name,
                        slug=tenant.slug,
                        timezone=tenant.timezone,
                        role=role.value,
                    )
                )

    return {"user": _user_out(user), "workspaces": workspace_list}


@router.post("/forgot-password", summary="Request a password reset link")
async def forgot_password(request: LoginRequest, settings: SettingsDep) -> dict[str, Any]:
    """Answers identically whether or not the address exists.

    Otherwise this endpoint becomes a way to discover who has an account.
    """
    with global_session(settings) as session:
        result = auth.begin_password_reset(session, request.email)
        if result is not None:
            user, token = result
            session.flush()
            address = user.email

    if result is not None:
        tasks.queue_email(mail.password_reset_email(settings, address, token))

    return {
        "status": "If that address has an account, a reset link is on its way.",
        "dev_reset_token": _dev_token(settings, token) if result is not None else None,
    }


@router.post("/reset-password", summary="Set a new password from a reset link")
async def reset_password(
    request: ResetRequest, response: Response, settings: SettingsDep
) -> dict[str, Any]:
    try:
        with global_session(settings) as session:
            user = auth.complete_password_reset(session, request.token, request.password)
            session.flush()
            payload = _user_out(user)
            token, _ = create_access_token(settings, user.id)
    except TokenNotUsable as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except WeakPassword as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.problems) from exc

    _set_session_cookie(response, settings, token)
    return {"user": payload, "access_token": token, "token_type": "bearer"}


@router.post("/change-password", summary="Change the password while signed in")
async def change_password(
    request: ChangePasswordRequest, user: CurrentUser, settings: SettingsDep
) -> dict[str, str]:
    try:
        with global_session(settings) as session:
            stored = session.get(User, user.id)
            if stored is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="account not found")
            auth.change_password(session, stored, request.current_password, request.new_password)
    except InvalidCredentials as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except WeakPassword as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.problems) from exc

    return {"status": "password changed"}


@router.delete("/me", summary="Delete the account and purge its data")
async def delete_me(user: CurrentUser, response: Response, settings: SettingsDep) -> dict[str, Any]:
    """GDPR account deletion (M1 FE-3).

    Workspaces with other members survive and lose this member. Workspaces nobody
    else belongs to are deleted outright, cascading to all of their data.
    """
    result = auth.delete_account(settings, user.id)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"status": "account deleted", **result}
