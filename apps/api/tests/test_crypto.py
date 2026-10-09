"""Per-tenant credential encryption.

Shopify access tokens must be recoverable (we send them back to Shopify), so they
cannot be hashed like a password. These tests cover the properties that make
storing them acceptable.
"""

import uuid

import pytest

from sendox_api.config import Settings
from sendox_api.crypto import DecryptionFailed, decrypt_for_tenant, encrypt_for_tenant


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", log_level="WARNING")


def test_a_token_survives_a_round_trip(settings: Settings) -> None:
    tenant = uuid.uuid4()
    token = "shpat_" + "a" * 32

    assert (
        decrypt_for_tenant(settings, tenant, encrypt_for_tenant(settings, tenant, token)) == token
    )


def test_the_ciphertext_does_not_contain_the_token(settings: Settings) -> None:
    tenant = uuid.uuid4()
    token = "shpat_supersecretvalue"

    stored = encrypt_for_tenant(settings, tenant, token)

    assert token not in stored
    assert "supersecret" not in stored


def test_encrypting_twice_gives_different_ciphertexts(settings: Settings) -> None:
    """A fresh nonce each time, so identical tokens are not identifiable as equal."""
    tenant = uuid.uuid4()

    first = encrypt_for_tenant(settings, tenant, "same-token")
    second = encrypt_for_tenant(settings, tenant, "same-token")

    assert first != second


def test_another_workspace_cannot_decrypt_it(settings: Settings) -> None:
    """The point of per-tenant keys: one leaked key exposes one workspace."""
    owner, other = uuid.uuid4(), uuid.uuid4()
    stored = encrypt_for_tenant(settings, owner, "shpat_private")

    with pytest.raises(DecryptionFailed):
        decrypt_for_tenant(settings, other, stored)


def test_a_tampered_ciphertext_is_rejected_not_mangled(settings: Settings) -> None:
    """AES-GCM is authenticated, so corruption fails loudly rather than silently."""
    tenant = uuid.uuid4()
    stored = encrypt_for_tenant(settings, tenant, "shpat_private")
    tampered = stored[:-4] + ("AAAA" if not stored.endswith("AAAA") else "BBBB")

    with pytest.raises(DecryptionFailed):
        decrypt_for_tenant(settings, tenant, tampered)


def test_a_different_master_secret_cannot_decrypt(settings: Settings) -> None:
    tenant = uuid.uuid4()
    stored = encrypt_for_tenant(settings, tenant, "shpat_private")
    rotated = Settings(env="test", log_level="WARNING", encryption_key="a-completely-different-key")

    with pytest.raises(DecryptionFailed):
        decrypt_for_tenant(rotated, tenant, stored)


def test_production_refuses_the_default_encryption_key() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as caught:
        Settings(env="production", jwt_secret="x" * 48, _env_file=None)

    assert "ENCRYPTION_KEY" in str(caught.value)
