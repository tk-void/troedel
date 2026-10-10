"""What Trödel needs from a language model, and nothing more.

One call: a prompt, a few photos, a JSON Schema. Back comes an object that
fits the schema. Every provider is an adapter to that; the rest of the app
does not know which one is in use.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

Schema = dict[str, Any]


@dataclass(frozen=True)
class Image:
    media_type: str
    data: bytes


@dataclass(frozen=True)
class Answer:
    data: dict[str, Any]
    model: str
    """The model that actually answered, as the provider names it."""


class ProviderError(RuntimeError):
    """The request failed and repeating it unchanged will not help.

    ``code`` is a short, stable word the interface translates; the message is
    technical detail for the log and for whoever debugs.
    """

    code = "failed"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class ProviderUnavailable(ProviderError):
    """Rate limit, quota, overload, network: worth trying again later."""

    code = "unavailable"


class ProviderNotConfigured(ProviderError):
    """``missing`` names what has to be supplied, so the settings page can
    say it instead of showing a button that does nothing."""

    code = "not_configured"

    def __init__(self, message: str, missing: str = "") -> None:
        super().__init__(message)
        self.missing = missing


class Provider(Protocol):
    name: str

    def ask(self, prompt: str, *, system: str, schema: Schema, images: list[Image], model: str = "") -> Answer: ...


_UNSUPPORTED = ("minimum", "maximum", "multipleOf", "minLength", "maxLength", "minItems", "maxItems")


def strict(schema: Schema) -> Schema:
    """The schema in the form constrained decoding accepts: every object
    closed, no numeric or length limits. Those limits are still checked,
    by ``violations`` on the answer."""
    schema = copy.deepcopy(schema)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key in _UNSUPPORTED:
                node.pop(key, None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return schema


_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}


def violations(value: Any, schema: Schema, path: str = "answer") -> list[str]:
    """Where ``value`` does not fit ``schema``. Covers the part of JSON
    Schema this app uses; an unknown keyword is ignored, not an error."""
    found: list[str] = []
    kind = schema.get("type")
    if kind in _TYPES:
        ok = isinstance(value, _TYPES[kind])
        # bool is an int in Python, but true is not a number in JSON.
        if kind in ("integer", "number") and isinstance(value, bool):
            ok = False
        if not ok:
            return [f"{path}: expected {kind}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        found.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            found.append(f"{path}: {value} is below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            found.append(f"{path}: {value} is above {schema['maximum']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                found.append(f"{path}: missing {key!r}")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                found += violations(value[key], sub, f"{path}.{key}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value):
            found += violations(item, schema["items"], f"{path}[{i}]")
    return found


_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


def parse_object(text: str) -> dict[str, Any]:
    """The JSON object in a model's reply. Models asked for "only JSON"
    still like to wrap it in a code fence or add a sentence around it."""
    text = text.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ProviderError(f"no JSON object in the answer: {text[:120]!r}", "invalid") from None
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ProviderError(f"answer is not valid JSON: {exc}", "invalid") from exc
    if not isinstance(value, dict):
        raise ProviderError("answer is JSON, but not an object", "invalid")
    return value


def checked(value: dict[str, Any], schema: Schema) -> dict[str, Any]:
    problems = violations(value, schema)
    if problems:
        raise ProviderError("answer does not fit the schema: " + "; ".join(problems[:5]), "invalid")
    return value


def schema_instruction(schema: Schema) -> str:
    """For providers without constrained decoding: the schema as part of
    the prompt."""
    return (
        "Answer with a single JSON object and nothing else: no code fence, no explanation. "
        "It must be valid against this JSON Schema:\n" + json.dumps(schema, ensure_ascii=False)
    )
