"""The promise to buyers: the item in an edited photo is the item. These
tests pin that down pixel by pixel."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from troedel import imaging

from .conftest import FakeEditor, ellipse_mask, photo_bytes


def noisy(size: tuple[int, int] = (300, 240)) -> Image.Image:
    """An image in which every pixel differs, so that any resampling or
    filtering of the object would show."""
    image = Image.new("RGB", size)
    image.putdata(
        [
            ((x * 7 + y * 13) % 256, (x * 3 + y * 5) % 256, (x + y * 11) % 256)
            for y in range(size[1])
            for x in range(size[0])
        ]
    )
    return image


def hard_mask(size: tuple[int, int]) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rectangle((90, 60, 209, 179), fill=255)
    return mask


class TestRead:
    def test_metadata_is_left_behind(self, tmp_path: Path) -> None:
        source = Image.new("RGB", (64, 48), (10, 20, 30))
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"
        exif[0x0132] = "2026:01:01 10:00:00"
        buffer = io.BytesIO()
        source.save(buffer, "JPEG", exif=exif)
        assert b"PhoneMaker" in buffer.getvalue()

        name = imaging.store(imaging.read(buffer.getvalue()), tmp_path)
        for key in ("original", "original_t"):
            stored = imaging.paths(tmp_path, name)[key].read_bytes()
            assert b"PhoneMaker" not in stored and b"Exif" not in stored

    def test_rotation_from_exif_is_applied(self) -> None:
        source = Image.new("RGB", (80, 40))
        exif = Image.Exif()
        exif[0x0112] = 6
        buffer = io.BytesIO()
        source.save(buffer, "JPEG", exif=exif)
        assert imaging.read(buffer.getvalue()).size == (40, 80)

    def test_large_photos_are_shrunk(self) -> None:
        assert max(imaging.read(photo_bytes((4000, 3000))).size) == imaging.MAX_EDGE

    @pytest.mark.parametrize("data", [b"", b"not an image", b"<svg xmlns='http://www.w3.org/2000/svg'/>"])
    def test_rejects_what_is_not_a_photo(self, data: bytes) -> None:
        with pytest.raises(imaging.ImageError):
            imaging.read(data)

    def test_file_names_cannot_be_guessed(self) -> None:
        names = {imaging.new_name() for _ in range(200)}
        assert len(names) == 200 and all(len(n) == 16 for n in names)


class TestCutOut:
    def test_object_pixels_are_identical_on_white(self) -> None:
        image = noisy()
        result = imaging.on_white(image, hard_mask(image.size))
        margin = int(120 * imaging.MARGIN)
        cut = result.crop((margin, margin, margin + 120, margin + 120))
        assert ImageChops.difference(cut, image.crop((90, 60, 210, 180))).getbbox() is None
        assert result.getpixel((0, 0)) == imaging.WHITE and result.width == result.height

    def test_object_pixels_are_identical_in_the_studio(self) -> None:
        image = noisy()
        result = imaging.studio(image, hard_mask(image.size))
        side = result.width
        ox, oy = (side - 120) // 2, (side - 120) // 2 - int(side * 0.02)
        cut = result.crop((ox, oy, ox + 120, oy + 120))
        assert ImageChops.difference(cut, image.crop((90, 60, 210, 180))).getbbox() is None

    def test_studio_shadow_lies_below_the_object_only(self) -> None:
        image = noisy()
        result = imaging.studio(image, hard_mask(image.size))
        side = result.width
        below = result.getpixel((side // 2, (side + 120) // 2 + 2))
        above = result.getpixel((side // 2, 4))
        assert sum(below) < sum(above)

    @pytest.mark.parametrize("mask", [Image.new("L", (300, 240), 0), Image.new("L", (10, 10), 255)])
    def test_useless_mask_is_an_error_not_a_blank_picture(self, mask: Image.Image) -> None:
        with pytest.raises(imaging.ImageError):
            imaging.on_white(noisy(), mask)


class TestTidy:
    BOX = [{"what": "poster", "x0": 0, "y0": 0, "x1": 250, "y1": 250}]

    @staticmethod
    def green(image: Image.Image, hole: Image.Image) -> Image.Image:
        return Image.new("RGB", image.size, (0, 255, 0))

    def test_only_the_box_changes(self) -> None:
        image = noisy((600, 600))
        result = imaging.tidy(image, None, self.BOX, self.green)
        assert result.getpixel((40, 40)) == (0, 255, 0)
        far = (400, 400, 600, 600)
        assert ImageChops.difference(result.crop(far), image.crop(far)).getbbox() is None

    def test_the_object_survives_a_box_drawn_over_it(self) -> None:
        image = noisy((600, 600))
        mask = Image.new("L", image.size, 0)
        ImageDraw.Draw(mask).rectangle((50, 50, 120, 120), fill=255)
        result = imaging.tidy(image, mask, self.BOX, self.green)
        inside = (50, 50, 121, 121)
        assert ImageChops.difference(result.crop(inside), image.crop(inside)).getbbox() is None
        assert result.getpixel((10, 10)) == (0, 255, 0)

    def test_no_boxes_no_change(self) -> None:
        image = noisy()
        assert ImageChops.difference(imaging.tidy(image, None, [], self.green), image).getbbox() is None


class TestEditor:
    def test_mask_is_computed_once_and_reused(self, tmp_path: Path) -> None:
        editor = FakeEditor(tmp_path / "models")
        name = imaging.store(imaging.read(photo_bytes()), tmp_path)
        editor.produce(tmp_path, name, "studio")
        editor.produce(tmp_path, name, "white")
        editor.produce(tmp_path, name, "studio")
        assert editor.masks == 1
        p = imaging.paths(tmp_path, name)
        assert all(p[k].is_file() for k in ("studio", "studio_t", "white", "white_t", "mask"))

    def test_tidy_without_distractors_is_the_original(self, tmp_path: Path) -> None:
        editor = FakeEditor(tmp_path / "models")
        name = imaging.store(imaging.read(photo_bytes()), tmp_path)
        editor.produce(tmp_path, name, "tidy", [])
        p = imaging.paths(tmp_path, name)
        assert Image.open(p["tidy"]).size == Image.open(p["original"]).size and editor.masks == 0

    def test_discard_keeps_the_mask(self, tmp_path: Path) -> None:
        editor = FakeEditor(tmp_path / "models")
        name = imaging.store(imaging.read(photo_bytes()), tmp_path)
        editor.produce(tmp_path, name, "studio")
        imaging.discard_look(tmp_path, name, "studio")
        p = imaging.paths(tmp_path, name)
        assert not p["studio"].exists() and p["mask"].is_file()
        imaging.delete(tmp_path, name)
        assert not any(path.exists() for path in p.values())

    def test_unknown_look(self, tmp_path: Path) -> None:
        with pytest.raises(imaging.ImageError):
            FakeEditor(tmp_path).produce(tmp_path, "x", "sepia")

    def test_retouching_model_is_rejected_on_a_checksum_mismatch(self, tmp_path: Path, monkeypatch) -> None:
        import contextlib

        import httpx

        @contextlib.contextmanager
        def fake_stream(*args, **kwargs):
            yield httpx.Response(200, content=b"not the model", request=httpx.Request("GET", "https://example.com"))

        monkeypatch.setattr(httpx, "stream", fake_stream)
        target = tmp_path / "lama.onnx"
        with pytest.raises(imaging.ImageError, match="checksum"):
            imaging.fetch_lama(target)
        assert not target.exists() and not target.with_suffix(".part").exists()


def test_ellipse_helper_matches_photo_helper() -> None:
    assert ellipse_mask((40, 30)).getbbox() is not None
