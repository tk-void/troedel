"""Claude through the Anthropic API, with an API key.

Uses structured outputs, so the answer is guaranteed to parse and to carry
every required field. The photos go to Anthropic and nowhere else.
"""

from __future__ import annotations

import base64
import json

import anthropic

from .base import Answer, Image, ProviderError, ProviderNotConfigured, ProviderUnavailable, Schema, checked, strict

DEFAULT_MODEL = "claude-opus-5-5"
MODELS = {
    "claude-opus-5-5": "Opus 5.5",
    "claude-sonnet-5-5": "Sonnet 5.5",
    "claude-haiku-4-5": "Haiku 4.5",
}
"""Offered in the settings. Any other model id can be typed in."""

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _has_fallbacks(model: str) -> bool:
    """Models whose safety classifiers can decline a request and that can
    hand it to another model on the server instead."""
    return model.startswith(("claude-opus-5", "claude-sonnet-5-5", "claude-fable-5"))


def _has_effort(model: str) -> bool:
    return not model.startswith("claude-haiku")


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self, api_key: str, model: str = "", base_url: str = "", client: anthropic.Anthropic | None = None
    ) -> None:
        if not api_key and client is None:
            raise ProviderNotConfigured("no Anthropic API key", "api_key")
        self.model = model or DEFAULT_MODEL
        # Two retries on 429/5xx are built into the client; a listing is
        # written in the background, so waiting a little is fine.
        self.client = client or anthropic.Anthropic(api_key=api_key, base_url=base_url or None, timeout=180.0)

    def ask(self, prompt: str, *, system: str, schema: Schema, images: list[Image], model: str = "") -> Answer:
        model = model or self.model
        content: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image.media_type,
                    "data": base64.standard_b64encode(image.data).decode("ascii"),
                },
            }
            for image in images
        ]
        content.append({"type": "text", "text": prompt})
        output_config: dict = {"format": {"type": "json_schema", "schema": strict(schema)}}
        if _has_effort(model):
            # Reading a few photos and writing a short text does not need
            # deep reasoning; "medium" keeps the price estimate considered
            # without paying for more.
            output_config["effort"] = "medium"
        request: dict = {
            "model": model,
            "max_tokens": 16000,
            "system": system,
            "messages": [{"role": "user", "content": content}],
            "output_config": output_config,
        }
        try:
            if _has_fallbacks(model):
                # A photo of a kitchen knife or a toy gun can trip a
                # classifier. With this, the API retries on the model
                # Anthropic recommends instead of returning a refusal.
                response = self.client.beta.messages.create(**request, betas=[FALLBACK_BETA], fallbacks="default")
            else:
                response = self.client.messages.create(**request)
        except anthropic.AuthenticationError as exc:
            raise ProviderError(f"Anthropic rejected the API key: {exc.message}", "auth") from exc
        except anthropic.PermissionDeniedError as exc:
            raise ProviderError(f"Anthropic: not permitted: {exc.message}", "auth") from exc
        except anthropic.NotFoundError as exc:
            raise ProviderError(f"Anthropic does not know the model {model!r}: {exc.message}", "model") from exc
        except anthropic.RateLimitError as exc:
            raise ProviderUnavailable(f"Anthropic rate limit: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailable(f"Anthropic is having trouble ({exc.status_code})") from exc
            raise ProviderError(f"Anthropic refused the request ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderUnavailable(f"Anthropic not reachable: {exc}") from exc

        if response.stop_reason == "refusal":
            raise ProviderError("the model declined to answer for these photos", "declined")
        if response.stop_reason == "max_tokens":
            raise ProviderError("the answer was cut off", "invalid")
        text = next((block.text for block in response.content if block.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"answer is not valid JSON: {exc}", "invalid") from exc
        return Answer(checked(data, schema), response.model)
