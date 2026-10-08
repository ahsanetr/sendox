"""Claude client configuration handling.

No network: a missing key must produce a clear message rather than a stack trace
from inside a request handler, and that is testable without calling the API.
"""

import pytest

from sendox_api.clients import claude
from sendox_api.config import Settings


def test_not_configured_without_a_key() -> None:
    assert not claude.is_configured(Settings(anthropic_api_key=None))
    assert not claude.is_configured(Settings(anthropic_api_key=""))


def test_configured_with_a_key() -> None:
    assert claude.is_configured(Settings(anthropic_api_key="sk-ant-test"))


async def test_completing_without_a_key_raises_a_clear_error() -> None:
    with pytest.raises(claude.ClaudeNotConfigured) as caught:
        await claude.complete(Settings(anthropic_api_key=None), "hello")

    assert "ANTHROPIC_API_KEY" in str(caught.value)


def test_model_default_is_current() -> None:
    """The scope document names a model id that does not exist; this is the real one."""
    assert Settings(_env_file=None).anthropic_model == "claude-sonnet-5"
