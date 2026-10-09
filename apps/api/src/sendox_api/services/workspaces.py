"""Workspaces, membership and roles (scope M1 FE-4/5/7)."""

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sendox_api import security
from sendox_api.db import adopt_tenant
from sendox_api.models import Invitation, MemberRole, Membership, Tenant, User
from sendox_api.services import audit
from sendox_api.services.errors import (
    AlreadyAMember,
    AlreadyInvited,
    InsufficientRole,
    LastOwner,
    NotAMember,
    SlugTaken,
    TokenNotUsable,
)

# Ordered least to most privileged, so a required role is a simple comparison.
ROLE_RANK: dict[MemberRole, int] = {
    MemberRole.VIEWER: 0,
    MemberRole.EDITOR: 1,
    MemberRole.ADMIN: 2,
    MemberRole.OWNER: 3,
}


def role_allows(actual: MemberRole, required: MemberRole) -> bool:
    return ROLE_RANK[actual] >= ROLE_RANK[required]


def require_role(actual: MemberRole, required: MemberRole) -> None:
    if not role_allows(actual, required):
        raise InsufficientRole(required.value, actual.value)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug[:60] or "workspace"


def unique_slug(session: Session, name: str) -> str:
    base = slugify(name)
    candidate = base
    suffix = 2
    while session.execute(select(Tenant.id).where(Tenant.slug == candidate)).first() is not None:
        candidate = f"{base}-{suffix}"[:80]
        suffix += 1
        if suffix > 200:
            raise SlugTaken(base)
    return candidate


# ----------------------------------------------------------------- workspaces


def create_workspace(
    session: Session, owner: User, name: str, timezone: str = "UTC"
) -> tuple[Tenant, Membership]:
    """Create a workspace with its creator as owner.

    Called on a session with no tenant context, because the workspace has no id to
    scope to yet. Once the tenant row exists we adopt its context on the same
    transaction, which is what lets the owner's membership satisfy the row-level
    security policy instead of bypassing it.
    """
    tenant = Tenant(name=name.strip(), slug=unique_slug(session, name), timezone=timezone)
    session.add(tenant)
    session.flush()

    adopt_tenant(session, tenant.id, owner.id)

    membership = Membership(tenant_id=tenant.id, user_id=owner.id, role=MemberRole.OWNER)
    session.add(membership)
    session.flush()

    audit.record(
        session,
        tenant_id=tenant.id,
        actor_user_id=owner.id,
        action="workspace.created",
        target=tenant.slug,
        meta={"name": tenant.name, "timezone": tenant.timezone},
    )
    session.flush()
    return tenant, membership


def memberships_for_user(session: Session, user_id: uuid.UUID) -> list[Membership]:
    """Every workspace a person belongs to.

    Requires a `user_session`: the `own_memberships` policy is what makes these
    rows visible across workspace boundaries.
    """
    return list(
        session.execute(
            select(Membership).where(Membership.user_id == user_id).order_by(Membership.created_at)
        )
        .scalars()
        .all()
    )


def membership_in(session: Session, tenant_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    membership = session.execute(
        select(Membership).where(Membership.tenant_id == tenant_id, Membership.user_id == user_id)
    ).scalar_one_or_none()
    if membership is None:
        raise NotAMember("you do not have access to this workspace")
    return membership


def update_settings(
    session: Session,
    *,
    tenant: Tenant,
    actor: Membership,
    name: str | None = None,
    timezone: str | None = None,
) -> Tenant:
    require_role(actor.role, MemberRole.ADMIN)

    changed: dict[str, object] = {}
    if name is not None and name.strip() and name.strip() != tenant.name:
        changed["name"] = name.strip()
        tenant.name = name.strip()
    if timezone is not None and timezone != tenant.timezone:
        changed["timezone"] = timezone
        tenant.timezone = timezone

    if changed:
        audit.record(
            session,
            tenant_id=tenant.id,
            actor_user_id=actor.user_id,
            action="workspace.updated",
            target=tenant.slug,
            meta=changed,
        )
    return tenant


# ----------------------------------------------------------------- membership


def members(session: Session, tenant_id: uuid.UUID) -> list[Membership]:
    return list(
        session.execute(
            select(Membership)
            .where(Membership.tenant_id == tenant_id)
            .order_by(Membership.created_at)
        )
        .scalars()
        .all()
    )


def _owner_count(session: Session, tenant_id: uuid.UUID) -> int:
    return int(
        session.execute(
            select(func.count())
            .select_from(Membership)
            .where(Membership.tenant_id == tenant_id, Membership.role == MemberRole.OWNER)
        ).scalar_one()
    )


def change_role(
    session: Session, *, actor: Membership, target: Membership, role: MemberRole
) -> Membership:
    require_role(actor.role, MemberRole.ADMIN)

    # Only an owner may create or unmake another owner.
    if MemberRole.OWNER in (role, target.role):
        require_role(actor.role, MemberRole.OWNER)

    demoting_the_last_owner = (
        target.role is MemberRole.OWNER
        and role is not MemberRole.OWNER
        and _owner_count(session, target.tenant_id) <= 1
    )
    if demoting_the_last_owner:
        raise LastOwner("a workspace must keep at least one owner")

    previous = target.role
    target.role = role
    audit.record(
        session,
        tenant_id=target.tenant_id,
        actor_user_id=actor.user_id,
        action="member.role_changed",
        target=str(target.user_id),
        meta={"from": previous.value, "to": role.value},
    )
    return target


def remove_member(session: Session, *, actor: Membership, target: Membership) -> None:
    # Leaving voluntarily needs no privilege; removing someone else does.
    if actor.user_id != target.user_id:
        require_role(actor.role, MemberRole.ADMIN)
        if target.role is MemberRole.OWNER:
            require_role(actor.role, MemberRole.OWNER)

    if target.role is MemberRole.OWNER and _owner_count(session, target.tenant_id) <= 1:
        raise LastOwner("a workspace must keep at least one owner")

    audit.record(
        session,
        tenant_id=target.tenant_id,
        actor_user_id=actor.user_id,
        action="member.removed",
        target=str(target.user_id),
        meta={"role": target.role.value},
    )
    session.delete(target)


# ---------------------------------------------------------------- invitations


def invite(
    session: Session,
    *,
    actor: Membership,
    tenant: Tenant,
    email: str,
    role: MemberRole,
) -> tuple[Invitation, str]:
    """Create an invitation. Returns it with the plaintext token for the email."""
    require_role(actor.role, MemberRole.ADMIN)
    if role is MemberRole.OWNER:
        require_role(actor.role, MemberRole.OWNER)

    address = email.strip().lower()

    existing_user = session.execute(select(User).where(User.email == address)).scalar_one_or_none()
    if existing_user is not None:
        already = session.execute(
            select(Membership).where(
                Membership.tenant_id == tenant.id, Membership.user_id == existing_user.id
            )
        ).scalar_one_or_none()
        if already is not None:
            raise AlreadyAMember(address)

    # Always filtered by tenant_id: invitations carry no RLS policy, so scoping is
    # the query's job here (see models/invitation.py).
    pending = session.execute(
        select(Invitation).where(
            Invitation.tenant_id == tenant.id,
            Invitation.email == address,
            Invitation.accepted_at.is_(None),
        )
    ).scalar_one_or_none()
    if pending is not None and pending.expires_at > datetime.now(UTC):
        raise AlreadyInvited(address)
    if pending is not None:
        session.delete(pending)
        session.flush()

    token, token_hash = security.generate_email_token()
    invitation = Invitation(
        tenant_id=tenant.id,
        email=address,
        role=role,
        token_hash=token_hash,
        invited_by_user_id=actor.user_id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    session.add(invitation)
    audit.record(
        session,
        tenant_id=tenant.id,
        actor_user_id=actor.user_id,
        action="member.invited",
        target=address,
        meta={"role": role.value},
    )
    session.flush()
    return invitation, token


def pending_invitations(session: Session, tenant_id: uuid.UUID) -> list[Invitation]:
    return list(
        session.execute(
            select(Invitation)
            .where(Invitation.tenant_id == tenant_id, Invitation.accepted_at.is_(None))
            .order_by(Invitation.created_at)
        )
        .scalars()
        .all()
    )


def find_invitation(session: Session, token: str) -> Invitation:
    invitation = session.execute(
        select(Invitation).where(Invitation.token_hash == security.hash_email_token(token))
    ).scalar_one_or_none()

    if invitation is None or invitation.accepted_at is not None:
        raise TokenNotUsable("this invitation is not valid")
    if invitation.expires_at <= datetime.now(UTC):
        raise TokenNotUsable("this invitation has expired")
    return invitation


def accept_invitation(session: Session, *, invitation: Invitation, user: User) -> Membership:
    existing = session.execute(
        select(Membership).where(
            Membership.tenant_id == invitation.tenant_id, Membership.user_id == user.id
        )
    ).scalar_one_or_none()
    if existing is not None:
        invitation.accepted_at = datetime.now(UTC)
        raise AlreadyAMember(user.email)

    membership = Membership(tenant_id=invitation.tenant_id, user_id=user.id, role=invitation.role)
    session.add(membership)
    invitation.accepted_at = datetime.now(UTC)
    audit.record(
        session,
        tenant_id=invitation.tenant_id,
        actor_user_id=user.id,
        action="member.joined",
        target=user.email,
        meta={"role": invitation.role.value},
    )
    session.flush()
    return membership
