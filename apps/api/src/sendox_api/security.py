"""Password hashing, access tokens, and the one-time tokens sent by email.

Three distinct secrets-handling concerns live here so no route has to think about
them:

* passwords are hashed with Argon2id, never stored or logged in the clear;
* sessions are short-lived signed JWTs carrying a user id and nothing sensitive;
* email tokens (verification, password reset, invitations) are random strings we
  only ever store **hashed** — a leaked database row cannot be replayed as a link.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from sendox_api.config import Settings

_hasher = PasswordHash.recommended()

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(days=7)
EMAIL_TOKEN_TTL = timedelta(hours=24)
INVITATION_TTL = timedelta(days=7)
PASSWORD_RESET_TTL = timedelta(hours=1)

MIN_PASSWORD_LENGTH = 10


class TokenPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"


class InvalidToken(Exception):
    """A session token is missing, malformed, expired, or not ours."""


@dataclass(frozen=True, slots=True)
class SessionClaims:
    user_id: UUID
    issued_at: datetime
    expires_at: datetime


# ----------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _hasher.verify(password, hashed)


def password_problems(password: str) -> list[str]:
    """Human-readable reasons a password is unacceptable (scope M1 FE-1).

    Length first: it does more for real-world strength than character classes,
    which mostly teach people to write Password1!.
    """
    problems: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"must be at least {MIN_PASSWORD_LENGTH} characters")
    if password.lower() == password or password.upper() == password:
        problems.append("must mix upper and lower case")
    if not any(character.isdigit() for character in password):
        problems.append("must contain a digit")
    return problems


# -------------------------------------------------------------- session JWTs


def create_access_token(settings: Settings, user_id: UUID) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires_at = now + ACCESS_TOKEN_TTL
    token = jwt.encode(
        {
            "sub": str(user_id),
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "iss": "sendox",
        },
        settings.jwt_secret,
        algorithm=JWT_ALGORITHM,
    )
    return token, expires_at


def decode_access_token(settings: Settings, token: str) -> SessionClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            issuer="sendox",
            options={"require": ["sub", "exp", "iat"]},
        )
        return SessionClaims(
            user_id=UUID(payload["sub"]),
            issued_at=datetime.fromtimestamp(payload["iat"], UTC),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise InvalidToken(str(exc)) from exc


# ---------------------------------------------------------------- email tokens


def generate_email_token() -> tuple[str, str]:
    """Return (token to put in the link, hash to store).

    The plaintext exists only long enough to build the email.
    """
    token = secrets.token_urlsafe(32)
    return token, hash_email_token(token)


def hash_email_token(token: str) -> str:
    # SHA-256 is right here, not Argon2: the token is already 256 bits of
    # entropy, so there is nothing to brute-force and lookups stay indexable.
    return hashlib.sha256(token.encode()).hexdigest()


def token_expiry(purpose: TokenPurpose) -> datetime:
    ttl = EMAIL_TOKEN_TTL if purpose is TokenPurpose.VERIFY_EMAIL else PASSWORD_RESET_TTL
    return datetime.now(UTC) + ttl
