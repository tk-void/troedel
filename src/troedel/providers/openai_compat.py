"""Any service that speaks the OpenAI chat completions protocol.

That covers OpenAI itself, Google's Gemini through its compatibility
endpoint, OpenRouter, and local servers such as Ollama or LM Studio, which
keep the photos on the machine.

These services differ in how well they enforce a schema, so this adapter
does not rely on it: the schema goes into the prompt, the reply is parsed
tolerantly and checked here, and one failed check gets one retry with the
complaint attached.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from .base import (
    Answer,
    Image,
    ProviderError,
    ProviderNotConfigured,
    ProviderUnavailable,
    Schema,
    checked,
    parse_object,
    schema_instruction,
)

PRESETS: dict[str, dict[str, str]] = {
    "openai": {"base_url": "https://api.openai.com/v1", "model": ""},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-3.6-flash"},
    "ollama": {"base_url": "http://127.0.0.1:11434/v1", "model": ""},
    "custom": {"base_url": "", "model": ""},
}
"""Starting points. Base URL and model can be changed in the settings. A
model is only preset where one name is a safe guess; elsewhere the setup
asks, because model names age quickly and local servers serve whatever was
pulled."""

KEYLESS = {"ollama", "custom"}
"""Local servers usually want no key."""


class OpenAICompatProvider:
    def __init__(
        self, name: str, api_key: str, model: str = "", base_url: str = "", client: httpx.Client | None = None
    ) -> None:
        preset = PRESETS.get(name)
        if preset is None:
            raise ProviderNotConfigured(f"unknown provider {name!r}", "provider")
        self.name = name
        self.base_url = (base_url or preset["base_url"]).rstrip("/")
        self.model = model or preset["model"]
        if not self.base_url:
            raise ProviderNotConfigured("no base URL", "base_url")
        if not self.model:
            raise ProviderNotConfigured("no model", "model")
        if not api_key and name not in KEYLESS:
            raise ProviderNotConfigured("no API key", "api_key")
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0))

    def ask(self, prompt: str, *, system: str, schema: Schema, images: list[Image], model: str = "") -> Answer:
        model = model or self.model
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image in images:
            data = base64.standard_b64encode(image.data).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{image.media_type};base64,{data}"}})
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system + "\n\n" + schema_instruction(schema)},
            {"role": "user", "content": content},
        ]
        reply = self._complete(model, messages)
        try:
            return Answer(checked(parse_object(reply), schema), model)
        except ProviderError as first:
            messages += [
                {"role": "assistant", "content": reply},
                {
                    "role": "user",
                    "content": f"That did not work: {first}. Send the corrected JSON object, nothing else.",
                },
            ]
            reply = self._complete(model, messages)
            return Answer(checked(parse_object(reply), schema), model)

    def _complete(self, model: str, messages: list[dict[str, Any]]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {"model": model, "messages": messages, "response_format": {"type": "json_object"}}
        try:
            response = self.client.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{self.name} not reachable: {exc}") from exc
        if response.status_code in (401, 403):
            raise ProviderError(f"{self.name} rejected the API key ({response.status_code})", "auth")
        if response.status_code == 404:
            raise ProviderError(f"{self.name}: unknown model or address ({model!r}): {response.text[:200]}", "model")
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderUnavailable(f"{self.name} answered {response.status_code}: {response.text[:200]}")
        if response.status_code == 400 and "api key" in response.text.lower():
            # Google answers a bad key with 400, not 401.
            raise ProviderError(f"{self.name} rejected the API key: {response.text[:200]}", "auth")
        if response.status_code >= 400:
            raise ProviderError(f"{self.name} refused the request ({response.status_code}): {response.text[:300]}")
        try:
            choice = response.json()["choices"][0]
            text = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name}: unexpected reply: {response.text[:200]}", "invalid") from exc
        if not isinstance(text, str) or not text.strip():
            raise ProviderError(f"{self.name}: empty answer", "invalid")
        return text
