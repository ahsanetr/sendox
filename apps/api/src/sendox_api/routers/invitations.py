"""Accepting an invitation.

Separate from the workspace router on purpose: these endpoints are reached by
someone who is **not yet** a member, so they cannot sit behind the workspace
dependency that checks membership.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from sendox_api.db import global_session, tenant_session
from sendox_api.dependencies import CurrentUser, SettingsDep
from sendox_api.models import Tenant, User
from sendox_api.services import workspaces
from sendox_api.services.errors import AlreadyAMember, TokenNotUsable

router = APIRouter(prefix="/invitations", tags=["workspaces"])


class TokenBody(BaseModel):
    token: str = Field(min_length=10)


@router.post("/preview", summary="What does this invitation offer?")
async def preview(request: TokenBody, settings: SettingsDep) -> dict[str, Any]:
    """Unauthenticated: the recipient may not have an account yet.

    Reveals only the workspace name, the offered role and the invited address —
    enough to decide, and nothing about the workspace's contents.
    """
    with global_session(settings) as session:
        try:
            invitation = workspaces.find_invitation(session, request.token)
        except TokenNotUsable as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        tenant = session.get(Tenant, invitation.tenant_id)
        return {
            "email": invitation.email,
            "role": invitation.role.value,
            "workspace": tenant.name if tenant else None,
            "expires_at": invitation.expires_at,
        }


@router.post("/accept", summary="Join the workspace")
async def accept(request: TokenBody, user: CurrentUser, settings: SettingsDep) -> dict[str, Any]:
    with global_session(settings) as session:
        try:
            invitation = workspaces.find_invitation(session, request.token)
        except TokenNotUsable as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        if invitation.email != user.email:
            # Otherwise a leaked link would work for whoever happened to find it.
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"this invitation was sent to {invitation.email}",
            )
        tenant_id = invitation.tenant_id

    try:
        with tenant_session(settings, tenant_id, user.id) as session:
            stored_user = session.get(User, user.id)
            invitation = workspaces.find_invitation(session, request.token)
            if stored_user is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="account not found")
            membership = workspaces.accept_invitation(
                session, invitation=invitation, user=stored_user
            )
            role = membership.role.value
    except AlreadyAMember as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="you are already in this workspace"
        ) from exc

    with global_session(settings) as session:
        tenant = session.get(Tenant, tenant_id)
        name = tenant.name if tenant else None

    return {"status": "joined", "workspace": {"id": str(tenant_id), "name": name}, "role": role}
