"""Encryption for credentials we must store and later reuse.

Shopify access tokens cannot be hashed — we have to send them back to Shopify on
every request, so they must be recoverable. That makes them unlike passwords, and
the scope document asks for AES-256 with per-tenant keys (M3 FE-2).

Per-tenant keys matter: one leaked key then exposes one workspace's token rather
than every workspace's. Each key is derived from a single master secret and the
tenant id via HKDF, so there is still only one secret to rotate and no key table
to manage.
"""

import os
from base64 import urlsafe_b64decode, urlsafe_b64encode
from uuid import UUID

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from sendox_api.config import Settings

# AES-256-GCM: 32-byte key, 12-byte nonce. GCM is authenticated, so a tampered
# ciphertext fails to decrypt rather than silently yielding garbage.
KEY_BYTES = 32
NONCE_BYTES = 12


class DecryptionFailed(Exception):
    """Wrong key, corrupted data, or a tampered ciphertext."""


def _tenant_key(settings: Settings, tenant_id: UUID) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_BYTES,
        salt=str(tenant_id).encode(),
        info=b"sendox-credential-encryption-v1",
    ).derive(settings.encryption_key.encode())


def encrypt_for_tenant(settings: Settings, tenant_id: UUID, plaintext: str) -> str:
    """Return urlsafe-base64 of nonce || ciphertext, safe to store in a text column."""
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(_tenant_key(settings, tenant_id)).encrypt(
        nonce,
        plaintext.encode(),
        # The tenant id is authenticated but not encrypted, so a ciphertext moved
        # to another workspace's row fails to decrypt instead of being accepted.
        associated_data=str(tenant_id).encode(),
    )
    return urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt_for_tenant(settings: Settings, tenant_id: UUID, stored: str) -> str:
    try:
        raw = urlsafe_b64decode(stored.encode())
        nonce, ciphertext = raw[:NONCE_BYTES], raw[NONCE_BYTES:]
        plaintext = AESGCM(_tenant_key(settings, tenant_id)).decrypt(
            nonce, ciphertext, associated_data=str(tenant_id).encode()
        )
    except Exception as exc:
        raise DecryptionFailed(str(exc)) from exc
    return plaintext.decode()
