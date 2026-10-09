"""Request-scoped dependencies.

Settings are read off ``app.state`` rather than the module-level cache so that an
app built with ``create_app(settings)`` — tests, or any future second app in one
process — actually uses the settings it was given.

The auth dependencies below are the single place a request turns into "who is this
and what may they do here", so no route re-implements it.
"""

import uuid
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Path, Request, status

from sendox_api.config import Settings
from sendox_api.db import global_session, tenant_session, user_session
from sendox_api.models import MemberRole, Membership, Tenant, User
from sendox_api.security import InvalidToken, decode_access_token
from sendox_api.services import workspaces
from sendox_api.services.errors import InsufficientRole, NotAMember

UNAUTHENTICATED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    detail="sign in to continue",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_request_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_request_settings)]


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def current_user(
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
    sendox_session: Annotated[str | None, Cookie()] = None,
) -> User:
    """The signed-in user, from an Authorization header or the session cookie.

    Both are accepted: the browser uses an httpOnly cookie (nothing readable by
    page scripts), while scripts and the API docs use a bearer token.
    """
    token = _bearer(authorization) or sendox_session
    if not token:
        raise UNAUTHENTICATED

    try:
        claims = decode_access_token(settings, token)
    except InvalidToken as exc:
        raise UNAUTHENTICATED from exc

    with global_session(settings) as session:
        user = session.get(User, claims.user_id)
        if user is None or not user.is_active:
            raise UNAUTHENTICATED
        session.expunge(user)
    return user


CurrentUser = Annotated[User, Depends(current_user)]


class WorkspaceContext:
    """A verified membership in one workspace, plus the data to act on it.

    Holding the ids rather than live ORM objects keeps this safe to pass around
    after its session has closed; handlers open the session they need.
    """

    def __init__(self, user: User, tenant: Tenant, role: MemberRole) -> None:
        self.user = user
        self.user_id: uuid.UUID = user.id
        self.tenant = tenant
        self.tenant_id: uuid.UUID = tenant.id
        self.role = role

    def require(self, role: MemberRole) -> None:
        workspaces.require_role(self.role, role)


def workspace_context(
    settings: SettingsDep,
    user: CurrentUser,
    workspace_id: Annotated[uuid.UUID, Path()],
) -> WorkspaceContext:
    """Resolve and authorise the workspace named in the path.

    Membership is read through a user-scoped session, so a non-member gets a 404
    from the database's own policy rather than from a condition we remembered to
    write.
    """
    with user_session(settings, user.id) as session:
        membership = session.execute(
            Membership.__table__.select().where(
                Membership.tenant_id == workspace_id, Membership.user_id == user.id
            )
        ).first()
        if membership is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="workspace not found"
            ) from NotAMember(str(workspace_id))
        role = MemberRole(membership.role)

    with global_session(settings) as session:
        tenant = session.get(Tenant, workspace_id)
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="workspace not found")
        session.expunge(tenant)

    return WorkspaceContext(user=user, tenant=tenant, role=role)


Workspace = Annotated[WorkspaceContext, Depends(workspace_context)]


def require_role(role: MemberRole) -> object:
    """Dependency factory: `Depends(require_role(MemberRole.ADMIN))`."""

    def guard(workspace: Workspace) -> WorkspaceContext:
        try:
            workspace.require(role)
        except InsufficientRole as exc:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"this action requires the {exc.required} role; you are {exc.actual}",
            ) from exc
        return workspace

    return Depends(guard)


__all__ = [
    "CurrentUser",
    "SettingsDep",
    "Workspace",
    "WorkspaceContext",
    "current_user",
    "get_request_settings",
    "require_role",
    "tenant_session",
]
