from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageDraw

from troedel import imaging, markets
from troedel.config import Settings
from troedel.db import DB
from troedel.providers import Answer, ProviderError
from troedel.worker import Worker

DRAFT: dict[str, Any] = {
    "title": "Kinderschuhe Superfit Gr. 27",
    "description": "Kaum getragen.",
    "facts": ["Größe 27"],
    "category": "Familie, Kind & Baby > Kinderschuhe",
    "brand": "Superfit",
    "model": "",
    "size": "27",
    "color": "blau",
    "material": "Leder",
    "condition": "very_good",
    "defects": [],
    "price": 15,
    "price_min": 10,
    "price_max": 20,
    "price_reason": "Markenschuh, guter Zustand.",
    "shipping": "small",
    "search_terms": ["Kinderschuhe", "Superfit"],
    "to_check": ["Größe prüfen"],
}


class FakeProvider:
    """Answers from a script instead of a model and records what it was asked."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.answers: list[dict[str, Any] | Exception] = []

    def ask(self, prompt: str, *, system: str, schema: dict, images: list, model: str = "") -> Answer:
        self.calls.append({"prompt": prompt, "system": system, "schema": schema, "images": images, "model": model})
        answer = self.answers.pop(0) if self.answers else dict(DRAFT)
        if isinstance(answer, Exception):
            raise answer
        return Answer(answer, model or "fake-1")


class FakeEditor(imaging.Editor):
    """Cuts out with a fixed ellipse instead of a model."""

    def __init__(self, model_dir: Path) -> None:
        super().__init__("fake", model_dir, fill=lambda image, hole: Image.new("RGB", image.size, (0, 200, 0)))
        self.masks = 0

    def mask(self, image: Image.Image) -> Image.Image:
        self.masks += 1
        return ellipse_mask(image.size)


def ellipse_mask(size: tuple[int, int]) -> Image.Image:
    mask = Image.new("L", size, 0)
    w, h = size
    ImageDraw.Draw(mask).ellipse((w * 0.25, h * 0.25, w * 0.75, h * 0.75), fill=255)
    return mask


def photo_bytes(size: tuple[int, int] = (400, 300), color: tuple[int, int, int] = (180, 40, 40)) -> bytes:
    import io

    image = Image.new("RGB", size, (90, 90, 90))
    w, h = size
    ImageDraw.Draw(image).ellipse((w * 0.25, h * 0.25, w * 0.75, h * 0.75), fill=color)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=95)
    return buffer.getvalue()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", cutout=True)


@pytest.fixture
def db(settings: Settings) -> DB:
    return DB(settings.db_path)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def worker(db: DB, settings: Settings, provider: FakeProvider) -> Worker:
    return Worker(db, settings, markets.get("de"), lambda: provider, FakeEditor(settings.model_dir))


__all__ = ["DRAFT", "FakeEditor", "FakeProvider", "ProviderError", "ellipse_mask", "photo_bytes"]
