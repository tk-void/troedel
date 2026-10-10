"""Photos and a few words in, the fields of a listing out.

The language and the platform knowledge come from the market, the model from
the provider. This module holds what is the same everywhere: the shape of a
listing and what to tidy up in an answer.
"""

from __future__ import annotations

import json
from types import ModuleType
from typing import Any

from .providers import Image, Provider

CONDITIONS = ("new_with_tags", "new", "very_good", "good", "fair", "defective")
SHIPPING = ("small", "parcel_s", "parcel_m", "parcel_l", "pickup")
MAX_SEARCH_TERMS = 8

_text = {"type": "string"}
_list = {"type": "array", "items": {"type": "string"}}
_amount = {"type": "integer", "minimum": 0}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": _text,
        "description": _text,
        "facts": _list,
        "category": _text,
        "brand": _text,
        "model": _text,
        "size": _text,
        "color": _text,
        "material": _text,
        "condition": {"type": "string", "enum": list(CONDITIONS)},
        "defects": _list,
        "price": _amount,
        "price_min": _amount,
        "price_max": _amount,
        "price_reason": _text,
        "shipping": {"type": "string", "enum": list(SHIPPING)},
        "search_terms": _list,
        "to_check": _list,
    },
}
SCHEMA["required"] = list(SCHEMA["properties"])

DISTRACTOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "photos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "photo": {"type": "integer"},
                    "distractors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "what": {"type": "string"},
                                "x0": {"type": "integer"},
                                "y0": {"type": "integer"},
                                "x1": {"type": "integer"},
                                "y1": {"type": "integer"},
                            },
                            "required": ["what", "x0", "y0", "x1", "y1"],
                        },
                    },
                },
                "required": ["photo", "distractors"],
            },
        }
    },
    "required": ["photos"],
}


def clean(d: dict[str, Any]) -> dict[str, Any]:
    """What a schema cannot enforce: whitespace, empty entries, an ordered
    price range."""
    out = dict(d)
    for key, value in out.items():
        if isinstance(value, str):
            out[key] = value.strip()
        elif isinstance(value, list):
            out[key] = [str(x).strip() for x in value if str(x).strip()]
    out["search_terms"] = out.get("search_terms", [])[:MAX_SEARCH_TERMS]
    low, high = sorted((int(out.get("price_min") or 0), int(out.get("price_max") or 0)))
    out["price_min"], out["price_max"] = low, high
    return out


def _images(photos: list[bytes]) -> list[Image]:
    return [Image("image/jpeg", p) for p in photos]


def compose(
    provider: Provider,
    market: ModuleType,
    photos: list[bytes],
    keywords: str,
    product: str = "",
    note: str = "",
    previous: dict[str, Any] | None = None,
    model: str = "",
) -> dict[str, Any]:
    answer = provider.ask(
        market.compose_prompt(keywords, product, note, previous),
        system=market.SYSTEM,
        schema=SCHEMA,
        images=_images(photos),
        model=model,
    )
    data = clean(answer.data)
    data["_model"] = answer.model
    return data


def revise(
    provider: Provider, market: ModuleType, photos: list[bytes], data: dict[str, Any], instruction: str, model: str = ""
) -> dict[str, Any]:
    """Rework a listing as instructed, and only as instructed."""
    current = {key: data.get(key) for key in SCHEMA["properties"]}
    answer = provider.ask(
        market.revise_prompt(json.dumps(current, ensure_ascii=False, indent=1), instruction),
        system=market.REVISE_SYSTEM,
        schema=SCHEMA,
        images=_images(photos),
        model=model,
    )
    new = clean(answer.data)
    new["_model"] = answer.model
    return new


def _box(raw: dict[str, Any]) -> dict[str, Any] | None:
    try:
        x0, y0, x1, y1 = (max(0, min(1000, int(raw[k]))) for k in ("x0", "y0", "x1", "y1"))
    except (KeyError, TypeError, ValueError):
        return None
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    # Tiny or almost frame-filling boxes are misses: the first retouches
    # nothing visible, the second would replace the photo.
    area = (x1 - x0) * (y1 - y0) / 1_000_000
    if x1 - x0 < 5 or y1 - y0 < 5 or area > 0.5:
        return None
    return {"what": str(raw.get("what", ""))[:80], "x0": x0, "y0": y0, "x1": x1, "y1": y1}


def find_distractors(
    provider: Provider, market: ModuleType, photos: list[bytes], subject: str, model: str = ""
) -> list[list[dict[str, Any]]]:
    """Per photo, the boxes around what should be retouched away, in the
    order of the photos."""
    answer = provider.ask(
        market.distractor_prompt(len(photos), subject),
        system=market.DISTRACTOR_SYSTEM,
        schema=DISTRACTOR_SCHEMA,
        images=_images(photos),
        model=model,
    )
    out: list[list[dict[str, Any]]] = [[] for _ in photos]
    for entry in answer.data.get("photos") or []:
        i = int(entry.get("photo") or 0) - 1
        if 0 <= i < len(photos):
            out[i] = [b for b in map(_box, entry.get("distractors") or []) if b]
    return out
