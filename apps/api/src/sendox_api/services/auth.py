"""Registration, email verification, login and password reset (scope M1 FE-1/2/3).

Every function takes a Session so the caller controls the transaction, and none of
them send email directly — they return the plaintext token for the caller to hand
to a worker. That keeps a slow mail server out of the request path and makes the
whole module testable without SMTP.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from sendox_api import security
from sendox_api.config import Settings
from sendox_api.db import global_session, tenant_session, user_session
from sendox_api.models import EmailToken, Membership, Tenant, User
from sendox_api.security import TokenPurpose
from sendox_api.services.errors import (
    AccountInactive,
    EmailAlreadyRegistered,
    EmailNotVerified,
    InvalidCredentials,
    TokenNotUsable,
    WeakPassword,
)


def normalise_email(email: str) -> str:
    return email.strip().lower()


def find_by_email(session: Session, email: str) -> User | None:
    return session.execute(
        select(User).where(User.email == normalise_email(email))
    ).scalar_one_or_none()


def register(
    session: Session, email: str, password: str, full_name: str | None
) -> tuple[User, str]:
    """Create an unverified account. Returns the user and the verification token."""
    problems = security.password_problems(password)
    if problems:
        raise WeakPassword(problems)

    address = normalise_email(email)
    if find_by_email(session, address) is not None:
        raise EmailAlreadyRegistered(address)

    user = User(
        email=address,
        hashed_password=security.hash_password(password),
        full_name=(full_name or "").strip() or None,
    )
    session.add(user)
    session.flush()

    token = issue_email_token(session, user, TokenPurpose.VERIFY_EMAIL)
    return user, token


def issue_email_token(session: Session, user: User, purpose: TokenPurpose) -> str:
    """Mint a one-time token, invalidating any earlier unused one for that purpose."""
    session.execute(
        delete(EmailToken).where(
            EmailToken.user_id == user.id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
    )
    token, token_hash = security.generate_email_token()
    session.add(
        EmailToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=token_hash,
            expires_at=security.token_expiry(purpose),
        )
    )
    session.flush()
    return token


def _consume_token(session: Session, token: str, purpose: TokenPurpose) -> User:
    record = session.execute(
        select(EmailToken).where(
            EmailToken.token_hash == security.hash_email_token(token),
            EmailToken.purpose == purpose,
        )
    ).scalar_one_or_none()

    if record is None or record.used_at is not None:
        raise TokenNotUsable("this link is not valid")
    if record.expires_at <= datetime.now(UTC):
        raise TokenNotUsable("this link has expired")

    record.used_at = datetime.now(UTC)
    user = session.get(User, record.user_id)
    if user is None:
        raise TokenNotUsable("this link is not valid")
    return user


def verify_email(session: Session, token: str) -> User:
    user = _consume_token(session, token, TokenPurpose.VERIFY_EMAIL)
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    return user


def authenticate(session: Session, email: str, password: str) -> User:
    user = find_by_email(session, email)

    # Hash a dummy password when the account is unknown so the response time does
    # not reveal which addresses are registered.
    if user is None or user.hashed_password is None:
        security.verify_password(password, security.hash_password("timing-equaliser"))
        raise InvalidCredentials("email or password is incorrect")

    if not security.verify_password(password, user.hashed_password):
        raise InvalidCredentials("email or password is incorrect")
    if not user.is_active:
        raise AccountInactive("this account has been deactivated")
    if user.email_verified_at is None:
        raise EmailNotVerified("confirm your email address before signing in")

    return user


def begin_password_reset(session: Session, email: str) -> tuple[User, str] | None:
    """Returns None for an unknown address.

    The caller must respond identically either way, so an attacker cannot use the
    endpoint to enumerate registered addresses.
    """
    user = find_by_email(session, email)
    if user is None:
        return None
    return user, issue_email_token(session, user, TokenPurpose.RESET_PASSWORD)


def complete_password_reset(session: Session, token: str, new_password: str) -> User:
    problems = security.password_problems(new_password)
    if problems:
        raise WeakPassword(problems)

    user = _consume_token(session, token, TokenPurpose.RESET_PASSWORD)
    user.hashed_password = security.hash_password(new_password)

    # A reset also confirms control of the mailbox.
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)

    return user


def change_password(session: Session, user: User, current: str, new_password: str) -> None:
    if user.hashed_password is None or not security.verify_password(current, user.hashed_password):
        raise InvalidCredentials("current password is incorrect")

    problems = security.password_problems(new_password)
    if problems:
        raise WeakPassword(problems)

    user.hashed_password = security.hash_password(new_password)


def delete_account(settings: Settings, user_id: uuid.UUID) -> dict[str, int]:
    """Erase an account and every workspace it solely owns (M1 FE-3, GDPR).

    Orchestrates its own sessions because the work spans three different scopes,
    and none of them is allowed to see everything:

    * which workspaces the person belongs to — only a `user_session` can read that
      (the `own_memberships` policy);
    * whether anyone else is left in each one — needs that workspace's context;
    * deleting the workspace and the user — the globally-scoped tables.

    Workspaces with other members survive and simply lose this member. Workspaces
    nobody else belongs to are deleted, which cascades to their memberships, audit
    history and, later, contacts and campaigns.
    """
    with user_session(settings, user_id) as session:
        tenant_ids = [
            membership.tenant_id
            for membership in session.execute(
                select(Membership).where(Membership.user_id == user_id)
            )
            .scalars()
            .all()
        ]

    orphaned: list[uuid.UUID] = []
    for tenant_id in tenant_ids:
        with tenant_session(settings, tenant_id, user_id) as session:
            others = session.execute(
                select(Membership.id).where(
                    Membership.tenant_id == tenant_id, Membership.user_id != user_id
                )
            ).first()
        if others is None:
            orphaned.append(tenant_id)

    with global_session(settings) as session:
        for tenant_id in orphaned:
            tenant = session.get(Tenant, tenant_id)
            if tenant is not None:
                session.delete(tenant)

        session.execute(delete(EmailToken).where(EmailToken.user_id == user_id))
        user = session.get(User, user_id)
        if user is not None:
            session.delete(user)

    return {
        "workspaces_deleted": len(orphaned),
        "memberships_removed": len(tenant_ids),
    }
