"""Workspace, member and invitation endpoints (scope M1 FE-4/5/7)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from sendox_api import email as mail
from sendox_api import tasks
from sendox_api.db import global_session, tenant_session
from sendox_api.dependencies import CurrentUser, SettingsDep, Workspace
from sendox_api.models import AuditLog, MemberRole, Tenant, User
from sendox_api.services import workspaces
from sendox_api.services.errors import (
    AlreadyAMember,
    AlreadyInvited,
    InsufficientRole,
    LastOwner,
    NotAMember,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    timezone: str = Field(default="UTC", max_length=64)


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    timezone: str | None = Field(default=None, max_length=64)


class InviteRequest(BaseModel):
    email: EmailStr
    role: MemberRole = MemberRole.VIEWER


class RoleRequest(BaseModel):
    role: MemberRole


class MemberOut(BaseModel):
    user_id: str
    email: str | None
    full_name: str | None
    role: str
    joined_at: datetime


class InvitationOut(BaseModel):
    id: str
    email: str
    role: str
    expires_at: datetime


class AuditEntryOut(BaseModel):
    action: str
    target: str | None
    actor_user_id: str | None
    meta: dict[str, Any]
    at: datetime


def _http_role_error(exc: InsufficientRole) -> HTTPException:
    return HTTPException(
        status.HTTP_403_FORBIDDEN,
        detail=f"this action requires the {exc.required} role; you are {exc.actual}",
    )


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a workspace")
async def create(
    request: CreateWorkspaceRequest, user: CurrentUser, settings: SettingsDep
) -> dict[str, Any]:
    with global_session(settings) as session:
        stored = session.get(User, user.id)
        if stored is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="account not found")
        tenant, membership = workspaces.create_workspace(
            session, stored, request.name, request.timezone
        )
        session.flush()
        payload = {
            "id": str(tenant.id),
            "name": tenant.name,
            "slug": tenant.slug,
            "timezone": tenant.timezone,
            "role": membership.role.value,
        }
    return payload


@router.get("/{workspace_id}", summary="One workspace")
async def detail(workspace: Workspace) -> dict[str, Any]:
    return {
        "id": str(workspace.tenant_id),
        "name": workspace.tenant.name,
        "slug": workspace.tenant.slug,
        "timezone": workspace.tenant.timezone,
        "role": workspace.role.value,
    }


@router.patch("/{workspace_id}", summary="Update workspace settings")
async def update(
    request: UpdateWorkspaceRequest, workspace: Workspace, settings: SettingsDep
) -> dict[str, Any]:
    try:
        with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
            tenant = session.get(Tenant, workspace.tenant_id)
            if tenant is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="workspace not found")
            actor = workspaces.membership_in(session, workspace.tenant_id, workspace.user_id)
            workspaces.update_settings(
                session,
                tenant=tenant,
                actor=actor,
                name=request.name,
                timezone=request.timezone,
            )
            session.flush()
            payload = {
                "id": str(tenant.id),
                "name": tenant.name,
                "slug": tenant.slug,
                "timezone": tenant.timezone,
                "role": actor.role.value,
            }
    except InsufficientRole as exc:
        raise _http_role_error(exc) from exc
    return payload


@router.get("/{workspace_id}/members", summary="Who is in this workspace")
async def list_members(workspace: Workspace, settings: SettingsDep) -> list[MemberOut]:
    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        rows = [
            (member.user_id, member.role.value, member.created_at)
            for member in workspaces.members(session, workspace.tenant_id)
        ]

    # Users are global, so their names come from a session with no tenant context.
    with global_session(settings) as session:
        out: list[MemberOut] = []
        for user_id, role, joined_at in rows:
            member_user = session.get(User, user_id)
            out.append(
                MemberOut(
                    user_id=str(user_id),
                    email=member_user.email if member_user else None,
                    full_name=member_user.full_name if member_user else None,
                    role=role,
                    joined_at=joined_at,
                )
            )
    return out


@router.patch("/{workspace_id}/members/{member_user_id}", summary="Change a member's role")
async def set_role(
    member_user_id: Annotated[uuid.UUID, Field()],
    request: RoleRequest,
    workspace: Workspace,
    settings: SettingsDep,
) -> dict[str, str]:
    try:
        with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
            actor = workspaces.membership_in(session, workspace.tenant_id, workspace.user_id)
            target = workspaces.membership_in(session, workspace.tenant_id, member_user_id)
            workspaces.change_role(session, actor=actor, target=target, role=request.role)
    except NotAMember as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not a member") from exc
    except InsufficientRole as exc:
        raise _http_role_error(exc) from exc
    except LastOwner as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return {"status": "role updated", "role": request.role.value}


@router.delete("/{workspace_id}/members/{member_user_id}", summary="Remove a member")
async def remove_member(
    member_user_id: Annotated[uuid.UUID, Field()],
    workspace: Workspace,
    settings: SettingsDep,
) -> dict[str, str]:
    try:
        with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
            actor = workspaces.membership_in(session, workspace.tenant_id, workspace.user_id)
            target = workspaces.membership_in(session, workspace.tenant_id, member_user_id)
            workspaces.remove_member(session, actor=actor, target=target)
    except NotAMember as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not a member") from exc
    except InsufficientRole as exc:
        raise _http_role_error(exc) from exc
    except LastOwner as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return {"status": "member removed"}


@router.post(
    "/{workspace_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    summary="Invite someone to this workspace",
)
async def create_invitation(
    request: InviteRequest, workspace: Workspace, settings: SettingsDep
) -> dict[str, Any]:
    try:
        with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
            actor = workspaces.membership_in(session, workspace.tenant_id, workspace.user_id)
            tenant = session.get(Tenant, workspace.tenant_id)
            if tenant is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="workspace not found")
            invitation, token = workspaces.invite(
                session,
                actor=actor,
                tenant=tenant,
                email=request.email,
                role=request.role,
            )
            session.flush()
            payload = InvitationOut(
                id=str(invitation.id),
                email=invitation.email,
                role=invitation.role.value,
                expires_at=invitation.expires_at,
            )
            workspace_name = tenant.name
    except InsufficientRole as exc:
        raise _http_role_error(exc) from exc
    except AlreadyAMember as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="that person is already in this workspace"
        ) from exc
    except AlreadyInvited as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="that address already has a pending invitation"
        ) from exc

    tasks.queue_email(
        mail.invitation_email(
            settings,
            payload.email,
            token,
            workspace_name,
            payload.role,
            workspace.user.full_name or workspace.user.email,
        )
    )
    return {
        "invitation": payload,
        "dev_hint": None
        if settings.is_production
        else "Mailpit (Docker stack) shows the email at http://localhost:8025.",
        # Development only, so an invitation can be accepted without a mail server.
        "dev_invitation_token": None if settings.is_production else token,
    }


@router.get("/{workspace_id}/invitations", summary="Pending invitations")
async def list_invitations(workspace: Workspace, settings: SettingsDep) -> list[InvitationOut]:
    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        return [
            InvitationOut(
                id=str(invitation.id),
                email=invitation.email,
                role=invitation.role.value,
                expires_at=invitation.expires_at,
            )
            for invitation in workspaces.pending_invitations(session, workspace.tenant_id)
        ]


@router.get("/{workspace_id}/audit", summary="Workspace activity log")
async def audit_log(workspace: Workspace, settings: SettingsDep) -> list[AuditEntryOut]:
    """Owners and admins only — it names who did what."""
    try:
        workspace.require(MemberRole.ADMIN)
    except InsufficientRole as exc:
        raise _http_role_error(exc) from exc

    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        entries = (
            session.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100))
            .scalars()
            .all()
        )
        return [
            AuditEntryOut(
                action=entry.action,
                target=entry.target,
                actor_user_id=str(entry.actor_user_id) if entry.actor_user_id else None,
                meta=entry.meta,
                at=entry.created_at,
            )
            for entry in entries
        ]
