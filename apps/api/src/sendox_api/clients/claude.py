"""Anthropic Claude client.

Thin on purpose: the agents (Strategy, Copywriting, Optimization) each own their
prompts, and this module owns only the transport, the model choice and the "is it
configured?" question — so a missing API key is a clear message rather than a
stack trace from inside a request handler.
"""

from dataclasses import dataclass

from anthropic import AnthropicError, AsyncAnthropic

from sendox_api.config import Settings

REQUEST_TIMEOUT_SECONDS = 60.0

# Thinking tokens count against max_tokens, so a tight ceiling truncates the
# answer rather than merely shortening it.
DEFAULT_MAX_TOKENS = 16000


class ClaudeNotConfigured(RuntimeError):
    """No API key is set, so no generation can be attempted."""


class ClaudeCallFailed(RuntimeError):
    """The API rejected or failed the request."""


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


def is_configured(settings: Settings) -> bool:
    return bool(settings.anthropic_api_key)


def _client(settings: Settings) -> AsyncAnthropic:
    if not settings.anthropic_api_key:
        raise ClaudeNotConfigured(
            "ANTHROPIC_API_KEY is not set. Add it to .env to enable AI generation."
        )
    return AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=REQUEST_TIMEOUT_SECONDS)


async def complete(
    settings: Settings,
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Completion:
    """One-shot completion. Agents build the prompt; this just sends it.

    `max_tokens` is deliberately generous. Thinking tokens count against it, so a
    small ceiling can be consumed entirely by reasoning and return empty text —
    the failure looks like the model ignoring you.
    """
    client = _client(settings)
    try:
        message = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=max_tokens,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
    except AnthropicError as exc:
        raise ClaudeCallFailed(str(exc)) from exc

    text = "".join(block.text for block in message.content if block.type == "text")
    return Completion(
        text=text,
        model=message.model,
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
    )
