"""Shopify OAuth — the parts an attacker would go after.

The callback is unauthenticated by necessity: the browser returning from Shopify
may carry no session cookie. Everything it trusts is therefore proven
cryptographically, and these tests cover each proof.
"""

import hmac
import uuid
from hashlib import sha256

import pytest

from sendox_api.config import Settings
from sendox_api.services import shopify_oauth
from sendox_api.services.shopify_oauth import (
    InvalidCallback,
    InvalidShopDomain,
    ShopifyNotConfigured,
)

SECRET = "shpss_testsecret"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        log_level="WARNING",
        shopify_api_key="test-client-id",
        shopify_api_secret=SECRET,
        public_base_url="https://tunnel.example.com",
    )


def _sign(params: dict[str, str]) -> str:
    message = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if k != "hmac")
    return hmac.new(SECRET.encode(), message.encode(), sha256).hexdigest()


# ------------------------------------------------------------- shop domain


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("northwind.myshopify.com", "northwind.myshopify.com"),
        ("https://northwind.myshopify.com", "northwind.myshopify.com"),
        ("https://northwind.myshopify.com/admin", "northwind.myshopify.com"),
        ("  NorthWind.MyShopify.com  ", "northwind.myshopify.com"),
        ("northwind", "northwind.myshopify.com"),
    ],
)
def test_shop_domains_are_normalised(given: str, expected: str) -> None:
    assert shopify_oauth.normalise_shop_domain(given) == expected


@pytest.mark.parametrize(
    "hostile",
    [
        "evil.com",
        "northwind.myshopify.com.evil.com",
        "evil.com/northwind.myshopify.com",
        "northwind.myshopify.com@evil.com",
        "-leading-hyphen.myshopify.com",
        "",
        "..myshopify.com",
    ],
)
def test_domains_that_are_not_shopify_stores_are_refused(hostile: str) -> None:
    """The domain builds both the redirect URL and the URL we post the secret to."""
    with pytest.raises(InvalidShopDomain):
        shopify_oauth.normalise_shop_domain(hostile)


# -------------------------------------------------------------------- HMAC


def test_a_genuine_shopify_signature_verifies(settings: Settings) -> None:
    params = {"code": "abc123", "shop": "northwind.myshopify.com", "timestamp": "1700000000"}
    params["hmac"] = _sign(params)

    assert shopify_oauth.verify_hmac(settings, params)


def test_an_edited_parameter_breaks_the_signature(settings: Settings) -> None:
    params = {"code": "abc123", "shop": "northwind.myshopify.com", "timestamp": "1700000000"}
    params["hmac"] = _sign(params)

    params["shop"] = "attacker.myshopify.com"

    assert not shopify_oauth.verify_hmac(settings, params)


def test_a_missing_signature_is_not_treated_as_valid(settings: Settings) -> None:
    assert not shopify_oauth.verify_hmac(settings, {"code": "abc", "shop": "x.myshopify.com"})


def test_an_added_parameter_breaks_the_signature(settings: Settings) -> None:
    """Every parameter is signed, so smuggling one in must fail."""
    params = {"code": "abc123", "shop": "northwind.myshopify.com"}
    params["hmac"] = _sign(params)

    params["state"] = "injected"

    assert not shopify_oauth.verify_hmac(settings, params)


# ------------------------------------------------------------------- state


def test_state_round_trips_the_workspace_it_belongs_to(settings: Settings) -> None:
    tenant = uuid.uuid4()

    assert shopify_oauth.read_state(settings, shopify_oauth.issue_state(settings, tenant)) == tenant


def test_state_signed_with_another_secret_is_rejected(settings: Settings) -> None:
    """Otherwise anyone could point an install at a workspace of their choosing."""
    forged = shopify_oauth.issue_state(
        Settings(env="test", jwt_secret="a-different-signing-key-entirely", _env_file=None),
        uuid.uuid4(),
    )

    with pytest.raises(InvalidCallback):
        shopify_oauth.read_state(settings, forged)


@pytest.mark.parametrize("junk", ["", "not-a-jwt", "a.b.c"])
def test_malformed_state_is_rejected(settings: Settings, junk: str) -> None:
    with pytest.raises(InvalidCallback):
        shopify_oauth.read_state(settings, junk)


def test_each_state_is_unique(settings: Settings) -> None:
    tenant = uuid.uuid4()

    assert shopify_oauth.issue_state(settings, tenant) != shopify_oauth.issue_state(
        settings, tenant
    )


# --------------------------------------------------------------- authorize


def test_the_authorize_url_carries_everything_shopify_needs(settings: Settings) -> None:
    url = shopify_oauth.authorize_url(settings, "northwind.myshopify.com", "the-state")

    assert url.startswith("https://northwind.myshopify.com/admin/oauth/authorize?")
    assert "client_id=test-client-id" in url
    assert "state=the-state" in url
    assert "tunnel.example.com%2Fshopify%2Fcallback" in url


def test_connecting_without_a_public_url_explains_why(settings: Settings) -> None:
    """Shopify cannot redirect to localhost, and the error should say so."""
    local = Settings(env="test", shopify_api_key="k", shopify_api_secret="s", public_base_url=None)

    with pytest.raises(ShopifyNotConfigured) as caught:
        shopify_oauth.require_configured(local)

    assert "localhost" in str(caught.value)


def test_connecting_without_credentials_explains_why() -> None:
    # _env_file=None so the developer's own .env cannot make this pass or fail.
    with pytest.raises(ShopifyNotConfigured) as caught:
        shopify_oauth.require_configured(Settings(env="test", _env_file=None))

    assert "SHOPIFY_API_KEY" in str(caught.value)
