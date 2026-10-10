"""Read photos, shrink them, cut the object out.

Cutting out means: a model estimates the mask and nothing else. The object
itself comes pixel by pixel from the original. No generative step, no
inpainting, no colour correction. What a buyer sees of the item is real. At
the edges the soft mask blends object and background, and that is all.

Looks, chosen per item:

    studio    cut out, on a warm backdrop with a soft shadow
    white     cut out, on white
    tidy      the original photo with only the clutter in the background
              retouched away (people, posters, odds and ends). For things
              that cut out badly: playpens, bicycles.
    original  untouched

Files per photo (``<id>`` is a random name):

    <id>.jpg           original, rotated as EXIF says, without metadata
    <id>-studio.jpg    one file per look that has been produced
    <id>-white.jpg
    <id>-tidy.jpg
    <id>-mask.png      the mask, so that further looks need no new cut-out
    ...-t.jpg          thumbnail of each of the JPEGs above
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import logging
import os
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

log = logging.getLogger(__name__)

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover - HEIC is a convenience
    pass

# A phone photo has around 12 to 50 megapixels. Anything far beyond that is
# not a photo but an attempt to exhaust memory while decoding.
Image.MAX_IMAGE_PIXELS = 120_000_000

MAX_EDGE = 2560
THUMB_EDGE = 640
ANALYSIS_EDGE = 1568
"""Longer edge beyond which vision models downscale anyway."""
MARGIN = 0.08
"""Air around the cut-out object, as a share of the longer edge."""
WHITE = (255, 255, 255)
STUDIO_TOP, STUDIO_BOTTOM, STUDIO_CORNER = (250, 248, 245), (232, 227, 219), (214, 207, 196)
STUDIO_SHADOW = (70, 58, 45)
STUDIO_MARGIN = 0.12

EDITED_LOOKS = ("studio", "white", "tidy")
LAMA_SIDE = 512

LAMA_URL = "https://huggingface.co/Carve/LaMa-ONNX/resolve/c3c0c9e468934d62e79c329e35d82dd09ff8c444/lama_fp32.onnx"
LAMA_SHA256 = "1faef5301d78db7dda502fe59966957ec4b79dd64e16f03ed96913c7a4eb68d6"
"""LaMa (Apache-2.0) as ONNX. Pinned to a revision and checked against a
hash: the file comes from outside and is executed."""

Fill = Callable[[Image.Image, Image.Image], Image.Image]


class ImageError(ValueError):
    pass


def available() -> bool:
    """Whether the ``cutout`` extra is installed."""
    return importlib.util.find_spec("rembg") is not None


def new_name() -> str:
    return secrets.token_hex(8)


def read(data: bytes) -> Image.Image:
    """Uploaded file to RGB image, the right way up. Metadata (place,
    device, time) is left behind: ``save`` only writes it when asked to."""
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
    except Exception as exc:  # noqa: BLE001 - Pillow raises many kinds
        raise ImageError(f"not a readable image: {exc}") from exc
    image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
    return image


def paths(folder: Path, name: str) -> dict[str, Path]:
    out = {
        "original": folder / f"{name}.jpg",
        "original_t": folder / f"{name}-t.jpg",
        "mask": folder / f"{name}-mask.png",
    }
    for look in EDITED_LOOKS:
        out[look] = folder / f"{name}-{look}.jpg"
        out[f"{look}_t"] = folder / f"{name}-{look}-t.jpg"
    return out


def _thumbnail(image: Image.Image, path: Path) -> None:
    small = image.copy()
    small.thumbnail((THUMB_EDGE, THUMB_EDGE), Image.Resampling.LANCZOS)
    small.save(path, "JPEG", quality=82, optimize=True)


def store(image: Image.Image, folder: Path) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    name = new_name()
    p = paths(folder, name)
    image.save(p["original"], "JPEG", quality=92, optimize=True)
    _thumbnail(image, p["original_t"])
    return name


def for_analysis(folder: Path, name: str) -> bytes:
    image = Image.open(paths(folder, name)["original"])
    image.thumbnail((ANALYSIS_EDGE, ANALYSIS_EDGE), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=85)
    return buffer.getvalue()


def _object(image: Image.Image, mask: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Object and mask, cropped to the object."""
    mask = mask.convert("L")
    if mask.size != image.size:
        raise ImageError("mask does not match the image")
    box = mask.point(lambda v: 255 if v > 16 else 0).getbbox()
    if not box:
        raise ImageError("no object found")
    area = (box[2] - box[0]) * (box[3] - box[1]) / (image.width * image.height)
    if area < 0.01:
        raise ImageError("object found is too small")
    return image.crop(box), mask.crop(box)


def _studio_backdrop(side: int) -> Image.Image:
    """Light, warm ground: brighter at the top like the sweep in a photo
    studio, a little darker towards the corners."""
    gradient = Image.linear_gradient("L").resize((side, side))
    ground = Image.composite(
        Image.new("RGB", (side, side), STUDIO_BOTTOM), Image.new("RGB", (side, side), STUDIO_TOP), gradient
    )
    corners = Image.radial_gradient("L").resize((side, side)).point(lambda v: min(255, int(v * 0.35)))
    return Image.composite(Image.new("RGB", (side, side), STUDIO_CORNER), ground, corners)


def studio(image: Image.Image, mask: Image.Image) -> Image.Image:
    """Object on the studio backdrop with a soft shadow.

    On plain white an object often looks pasted, because nothing puts it on
    a floor. The shadow is made from the silhouette itself, slightly squashed
    and moved down, so it follows the lower edge even of things photographed
    at an angle. It lies on the backdrop only: the object is placed over it
    unchanged.
    """
    obj, m = _object(image, mask)
    w, h = obj.size
    side = int(max(w, h) * (1 + 2 * STUDIO_MARGIN))
    ox = (side - w) // 2
    oy = (side - h) // 2 - int(side * 0.02)

    def shadow(offset: float, blur: float, strength: float, squash: float) -> Image.Image:
        hs = max(1, int(h * squash))
        layer = Image.new("L", (side, side), 0)
        layer.paste(m.resize((w, hs)), (ox, oy + h - hs + int(side * offset)))
        return layer.filter(ImageFilter.GaussianBlur(side * blur)).point(lambda v: int(v * strength))

    # A tight contact shadow where the object stands, and a soft one around it.
    alpha = ImageChops.lighter(shadow(0.006, 0.006, 0.55, 0.92), shadow(0.022, 0.028, 0.26, 0.85))
    canvas = Image.composite(Image.new("RGB", (side, side), STUDIO_SHADOW), _studio_backdrop(side), alpha)
    canvas.paste(obj, (ox, oy), m)
    return canvas


def on_white(image: Image.Image, mask: Image.Image) -> Image.Image:
    """Object from the original on white, centred with a margin.

    Where the mask is fully opaque, the pixels are those of the original,
    unchanged: ``Image.composite`` only blends where the mask is between 0
    and 255, and nothing is scaled or filtered.
    """
    obj, m = _object(image, mask)
    cut = Image.composite(obj, Image.new("RGB", obj.size, WHITE), m)
    w, h = cut.size
    margin = int(max(w, h) * MARGIN)
    # Square: fits the grids of the marketplaces without their cropping
    # taking anything off the object.
    side = max(w, h) + 2 * margin
    canvas = Image.new("RGB", (side, side), WHITE)
    canvas.paste(cut, ((side - w) // 2, (side - h) // 2))
    return canvas


def _protected(object_mask: Image.Image | None, size: tuple[int, int]) -> Image.Image:
    """Where nothing is ever retouched: what the mask is sure belongs to the
    object, plus one pixel.

    Deliberately tight. With a generous margin the gaps between the bars of
    a playpen close up and a poster behind it stays, although it was marked
    correctly. A low threshold leaves a ghost, because the mask counts
    background that shows through as half object; only from about 240 up is
    it gone. Retouching only happens inside the marked boxes anyway."""
    if object_mask is None:
        return Image.new("L", size, 0)
    return object_mask.point(lambda v: 255 if v > 240 else 0).filter(ImageFilter.MaxFilter(3))


def tidy(image: Image.Image, object_mask: Image.Image | None, boxes: list[dict[str, Any]], fill: Fill) -> Image.Image:
    """Retouch the distractors away and touch nothing else.

    ``boxes`` are rectangles in 0..1000 from the model. For each, a crop with
    its surroundings is brought to 512x512, ``fill`` (LaMa) paints the hole,
    and only the hole goes back into the picture. The object is protected
    twice: it is taken out of the hole, and at the end it is laid over the
    result once more from the original.
    """
    width, height = image.size
    protected = _protected(object_mask, image.size)
    result = image.copy()
    for b in boxes:
        # The model's boxes are not pixel-exact, and a leftover (a sleeve,
        # the tips of someone's hair) is more noticeable than a hole that is
        # a little too large. So a generous margin; the object is safe.
        bw, bh = (b["x1"] - b["x0"]) * width / 1000, (b["y1"] - b["y0"]) * height / 1000
        rx, ry = 0.025 * max(width, height) + 0.15 * bw, 0.025 * max(width, height) + 0.15 * bh
        frame = (
            b["x0"] * width / 1000 - rx,
            b["y0"] * height / 1000 - ry,
            b["x1"] * width / 1000 + rx,
            b["y1"] * height / 1000 + ry,
        )
        hole = Image.new("L", image.size, 0)
        ImageDraw.Draw(hole).rectangle(frame, fill=255)
        hole = ImageChops.subtract(hole, protected)
        box = hole.getbbox()
        if not box:
            continue
        # A square crop with plenty of surroundings: LaMa needs context to
        # continue the edge of a table or a wall.
        side = min(max(width, height), max(LAMA_SIDE, int(max(box[2] - box[0], box[3] - box[1]) * 2.2)))
        cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
        x0 = min(max(0, cx - side // 2), max(0, width - side))
        y0 = min(max(0, cy - side // 2), max(0, height - side))
        crop = (x0, y0, min(width, x0 + side), min(height, y0 + side))
        part, part_hole = result.crop(crop), hole.crop(crop)
        square = (LAMA_SIDE, LAMA_SIDE)
        filled = fill(part.resize(square, Image.Resampling.LANCZOS), part_hole.resize(square)).resize(
            part.size, Image.Resampling.LANCZOS
        )
        blend = part_hole.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(2))
        result.paste(Image.composite(filled, part, blend), crop[:2])
    # What is protected comes from the original in the end, guaranteed.
    return Image.composite(image, result, protected)


def fetch_lama(target: Path) -> Path:
    """Download the retouching model once and check it. A file that does
    not match the hash is thrown away, never loaded."""
    if target.is_file():
        return target
    import httpx

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    digest = hashlib.sha256()
    log.info("Downloading the retouching model (about 200 MB), once")
    try:
        with httpx.stream("GET", LAMA_URL, follow_redirects=True, timeout=60.0) as response:
            response.raise_for_status()
            with partial.open("wb") as out:
                for chunk in response.iter_bytes(1 << 20):
                    digest.update(chunk)
                    out.write(chunk)
    except httpx.HTTPError as exc:
        partial.unlink(missing_ok=True)
        raise ImageError(f"could not download the retouching model: {exc}") from exc
    if digest.hexdigest() != LAMA_SHA256:
        partial.unlink(missing_ok=True)
        raise ImageError("the downloaded retouching model does not match its checksum")
    partial.replace(target)
    return target


class Retoucher:
    """LaMa paints holes plausibly. Fixed size 512x512."""

    def __init__(self, model_dir: Path) -> None:
        self.path = model_dir / "lama_fp32.onnx"
        self._session: Any = None

    def __call__(self, image: Image.Image, hole: Image.Image) -> Image.Image:
        import numpy as np
        import onnxruntime as ort

        if self._session is None:
            fetch_lama(self.path)
            log.info("Loading the retouching model")
            self._session = ort.InferenceSession(str(self.path), providers=["CPUExecutionProvider"])
        x = np.asarray(image.convert("RGB"), dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
        m = (np.asarray(hole.convert("L"), dtype=np.float32) > 127).astype(np.float32)[None, None]
        out = self._session.run(None, {"image": x, "mask": m})[0][0]
        # This export returns 0..255; others 0..1.
        if out.max() <= 1.5:
            out = out * 255
        return Image.fromarray(np.clip(out.transpose(1, 2, 0), 0, 255).astype(np.uint8))


class Editor:
    """Holds the model sessions. Loading takes seconds and a few hundred MB,
    so it happens with the first photo, not at start."""

    def __init__(self, model: str, model_dir: Path, fill: Fill | None = None) -> None:
        self.model = model
        self.model_dir = model_dir
        self._session: Any = None
        self.fill: Fill = fill or Retoucher(model_dir)

    def mask(self, image: Image.Image) -> Image.Image:
        # rembg reads this when it looks for (and downloads) its models.
        os.environ.setdefault("U2NET_HOME", str(self.model_dir))
        self.model_dir.mkdir(parents=True, exist_ok=True)
        from rembg import new_session, remove

        if self._session is None:
            log.info("Loading the cut-out model %s (downloaded on first use)", self.model)
            self._session = new_session(self.model)
        # only_mask: just the mask. The options that "clean" colours at the
        # edge or post-process the mask stay off: they would change the
        # object itself.
        return remove(image, session=self._session, only_mask=True)

    def _mask(self, image: Image.Image, p: dict[str, Path]) -> Image.Image:
        """The mask is the expensive part. Computed once, it is reused for
        every further look."""
        if p["mask"].is_file():
            return Image.open(p["mask"]).convert("L")
        mask = self.mask(image).convert("L")
        mask.save(p["mask"], optimize=True)
        return mask

    def produce(self, folder: Path, name: str, look: str, boxes: list[dict[str, Any]] | None = None) -> None:
        """Produces exactly one look. If it is there already, nothing
        happens, so switching back to an earlier look is instant."""
        if look not in EDITED_LOOKS:
            raise ImageError(f"unknown look {look!r}")
        p = paths(folder, name)
        if p[look].is_file():
            return
        image = Image.open(p["original"]).convert("RGB")
        if look == "tidy":
            # Nothing distracting found: the original is the result.
            result = tidy(image, self._mask(image, p), boxes, self.fill) if boxes else image
        else:
            result = (studio if look == "studio" else on_white)(image, self._mask(image, p))
        result.save(p[look], "JPEG", quality=95, optimize=True)
        _thumbnail(result, p[f"{look}_t"])


def discard_look(folder: Path, name: str, look: str) -> None:
    """Throw a look away so that it is produced again. The mask stays."""
    p = paths(folder, name)
    for key in (look, f"{look}_t"):
        if key in p:
            p[key].unlink(missing_ok=True)


def delete(folder: Path, name: str) -> None:
    for path in paths(folder, name).values():
        path.unlink(missing_ok=True)
