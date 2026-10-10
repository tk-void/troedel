"""Language model providers and the one place that picks between them."""

from __future__ import annotations

from dataclasses import dataclass

from . import anthropic_api, claude_cli, openai_compat
from .base import (
    Answer,
    Image,
    Provider,
    ProviderError,
    ProviderNotConfigured,
    ProviderUnavailable,
    Schema,
)

__all__ = [
    "Answer",
    "Image",
    "Provider",
    "ProviderError",
    "ProviderNotConfigured",
    "ProviderUnavailable",
    "Schema",
    "ProviderInfo",
    "PROVIDERS",
    "build",
]


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    needs_key: bool
    default_model: str
    default_base_url: str = ""
    models: tuple[str, ...] = ()
    local: bool = False
    """Photos stay on this machine or network."""
    experimental: bool = False


PROVIDERS: dict[str, ProviderInfo] = {
    "anthropic": ProviderInfo("anthropic", True, anthropic_api.DEFAULT_MODEL, models=tuple(anthropic_api.MODELS)),
    "gemini": ProviderInfo(
        "gemini", True, openai_compat.PRESETS["gemini"]["model"], openai_compat.PRESETS["gemini"]["base_url"]
    ),
    "openai": ProviderInfo(
        "openai", True, openai_compat.PRESETS["openai"]["model"], openai_compat.PRESETS["openai"]["base_url"]
    ),
    "ollama": ProviderInfo(
        "ollama",
        False,
        openai_compat.PRESETS["ollama"]["model"],
        openai_compat.PRESETS["ollama"]["base_url"],
        local=True,
    ),
    "custom": ProviderInfo("custom", False, "", local=False),
    "claude-cli": ProviderInfo(
        "claude-cli", False, claude_cli.DEFAULT_MODEL, models=tuple(claude_cli.MODELS), experimental=True
    ),
}


def build(provider: str, *, api_key: str = "", model: str = "", base_url: str = "") -> Provider:
    """The configured provider, or ``ProviderNotConfigured`` saying what is
    missing."""
    if not provider:
        raise ProviderNotConfigured("no AI provider chosen yet", "provider")
    if provider == "anthropic":
        return anthropic_api.AnthropicProvider(api_key, model, base_url)
    if provider == "claude-cli":
        return claude_cli.ClaudeCliProvider(model)
    if provider in openai_compat.PRESETS:
        return openai_compat.OpenAICompatProvider(provider, api_key, model, base_url)
    raise ProviderNotConfigured(f"unknown provider {provider!r}", "provider")
