#!/usr/bin/env python3
"""A demo instance with made-up items, for screenshots and for trying things.

    python tools/demo.py                 # fills ./demo-data and serves it
    python tools/demo.py --port 8123

Nothing here comes from a real household: the photos are drawn, the listings
are written below, no provider is asked and no model is downloaded. The
cut-out uses the outline the drawing already knows, so the looks appear
without the ``cutout`` extra. Sign in with the password this prints.

Screenshots in the README and the docs are taken from this instance and from
nowhere else (see CLAUDE.md).
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from troedel import imaging, markets  # noqa: E402
from troedel.auth import Auth  # noqa: E402
from troedel.config import Settings  # noqa: E402
from troedel.db import DB  # noqa: E402
from troedel.providers import Answer  # noqa: E402
from troedel.worker import Worker  # noqa: E402

PASSWORD = "troedel-demo-2026"  # noqa: S105 - a demo instance with drawn data
SETUP_CODE = "DEMODEMODEMO"
W, H = 1600, 1200
SS = 2
"""Everything is drawn at twice the size and scaled down: Pillow's shapes
have hard edges otherwise, and a cut-out along a jagged outline looks wrong."""

Color = tuple[int, int, int]
Draw = Callable[[Image.Image, float, float, float], None]


# -- drawing -------------------------------------------------------------------


def _mix(a: Color, b: Color, t: float) -> Color:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=True))  # type: ignore[return-value]


def _fill(layer: Image.Image, shape: Image.Image, color: Color, depth: float = 0.3) -> None:
    """Paint ``shape`` (an L mask) onto the layer, lit from the upper left:
    lighter there, darker towards the lower right."""
    box = shape.getbbox()
    if not box:
        return
    w, h = box[2] - box[0], box[3] - box[1]
    across = Image.linear_gradient("L").rotate(90, expand=True).resize((w, h))
    down = Image.linear_gradient("L").resize((w, h))
    ramp = ImageChops.add(across, down, scale=2)
    light, dark = _mix(color, (255, 255, 255), depth * 0.7), _mix(color, (0, 0, 0), depth)
    paint = Image.composite(Image.new("RGB", (w, h), dark), Image.new("RGB", (w, h), light), ramp)
    layer.paste(paint, box[:2], shape.crop(box))


def _shape(layer: Image.Image) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    mask = Image.new("L", layer.size, 0)
    return mask, ImageDraw.Draw(mask)


def vase(layer: Image.Image, cx: float, base: float, s: float) -> None:
    height = 560 * s
    left, right = [], []
    for i in range(81):
        t = i / 80
        belly = math.sin(math.pi * min(1.0, max(0.0, (t - 0.18) / 0.82)) ** 0.8) ** 1.3
        neck = 1 - min(1.0, t / 0.2)
        r = (52 + 150 * belly + 26 * neck**2) * s
        y = base - height * (1 - t)
        left.append((cx - r, y))
        right.append((cx + r, y))
    mask, d = _shape(layer)
    d.polygon(left + right[::-1], fill=255)
    _fill(layer, mask, (38, 120, 128), 0.42)
    glaze, d = _shape(layer)
    d.ellipse((cx - 95 * s, base - 380 * s, cx - 55 * s, base - 230 * s), fill=120)
    layer.paste((255, 255, 255), mask=glaze.filter(ImageFilter.GaussianBlur(14 * s)))
    rim, d = _shape(layer)
    d.ellipse((cx - 78 * s, base - height - 14 * s, cx + 78 * s, base - height + 14 * s), fill=255)
    _fill(layer, rim, (24, 78, 84), 0.2)


def lamp(layer: Image.Image, cx: float, base: float, s: float) -> None:
    green, brass = (46, 92, 70), (176, 142, 74)
    foot, d = _shape(layer)
    d.ellipse((cx - 150 * s, base - 46 * s, cx + 150 * s, base), fill=255)
    _fill(layer, foot, green, 0.35)
    elbow = (cx + 130 * s, base - 360 * s)
    head = (cx - 110 * s, base - 560 * s)
    arm, d = _shape(layer)
    d.line([(cx, base - 30 * s), elbow], fill=255, width=round(20 * s))
    d.line([elbow, head], fill=255, width=round(20 * s))
    _fill(layer, arm, brass, 0.3)
    joints, d = _shape(layer)
    for x, y in (elbow, head, (cx, base - 34 * s)):
        d.ellipse((x - 22 * s, y - 22 * s, x + 22 * s, y + 22 * s), fill=255)
    _fill(layer, joints, _mix(brass, (0, 0, 0), 0.25), 0.3)
    shade, d = _shape(layer)
    hx, hy = head
    d.polygon(
        [
            (hx - 40 * s, hy - 60 * s),
            (hx + 50 * s, hy - 40 * s),
            (hx - 60 * s, hy + 170 * s),
            (hx - 250 * s, hy + 110 * s),
        ],
        fill=255,
    )
    _fill(layer, shade, green, 0.4)
    glow, d = _shape(layer)
    d.ellipse((hx - 250 * s, hy + 96 * s, hx - 62 * s, hy + 176 * s), fill=255)
    _fill(layer, glow, (238, 226, 190), 0.12)


def _boot(layer: Image.Image, x: float, base: float, s: float, color: Color) -> None:
    outline = [
        (x - 80, base - 430), (x + 70, base - 430), (x + 78, base - 190), (x + 150, base - 130),
        (x + 250, base - 96), (x + 268, base - 40), (x + 250, base), (x - 84, base), (x - 96, base - 150),
    ]  # fmt: skip
    body, d = _shape(layer)
    d.polygon([(x + (px - x) * s, base + (py - base) * s) for px, py in outline], fill=255)
    body = body.filter(ImageFilter.GaussianBlur(10 * s)).point(lambda v: 255 if v > 120 else 0)
    _fill(layer, body, color, 0.34)
    sole, d = _shape(layer)
    d.rounded_rectangle((x - 92 * s, base - 30 * s, x + 262 * s, base), radius=14 * s, fill=255)
    _fill(layer, ImageChops.multiply(sole, body), _mix(color, (40, 30, 10), 0.6), 0.2)
    cuff, d = _shape(layer)
    d.rounded_rectangle((x - 86 * s, base - 440 * s, x + 76 * s, base - 396 * s), radius=12 * s, fill=255)
    _fill(layer, cuff, _mix(color, (255, 255, 255), 0.25), 0.25)


def boots(layer: Image.Image, cx: float, base: float, s: float) -> None:
    yellow = (232, 186, 34)
    _boot(layer, cx - 190 * s, base - 22 * s, s * 0.95, _mix(yellow, (0, 0, 0), 0.12))
    _boot(layer, cx - 40 * s, base, s, yellow)


def radio(layer: Image.Image, cx: float, base: float, s: float) -> None:
    w, h = 620 * s, 380 * s
    x0, y0 = cx - w / 2, base - h
    aerial, d = _shape(layer)
    d.line([(x0 + 70 * s, y0 + 10 * s), (x0 + 250 * s, y0 - 220 * s)], fill=255, width=round(8 * s))
    _fill(layer, aerial, (150, 150, 150), 0.3)
    body, d = _shape(layer)
    d.rounded_rectangle((x0, y0, x0 + w, base), radius=42 * s, fill=255)
    _fill(layer, body, (126, 82, 48), 0.36)
    panel, d = _shape(layer)
    d.rounded_rectangle((x0 + 34 * s, y0 + 34 * s, x0 + w - 34 * s, base - 34 * s), radius=24 * s, fill=255)
    _fill(layer, panel, (232, 220, 196), 0.16)
    grille, d = _shape(layer)
    for row in range(9):
        for col in range(10):
            x, y = x0 + (78 + col * 30) * s, y0 + (76 + row * 28) * s
            d.ellipse((x - 9 * s, y - 9 * s, x + 9 * s, y + 9 * s), fill=255)
    _fill(layer, grille, (70, 52, 38), 0.2)
    dial, d = _shape(layer)
    dx, dy = x0 + w - 150 * s, y0 + 150 * s
    d.ellipse((dx - 86 * s, dy - 86 * s, dx + 86 * s, dy + 86 * s), fill=255)
    _fill(layer, dial, (48, 44, 40), 0.3)
    marks, d = _shape(layer)
    for i in range(12):
        a = math.radians(210 - i * 22)
        d.line(
            [
                (dx + 58 * s * math.cos(a), dy - 58 * s * math.sin(a)),
                (dx + 72 * s * math.cos(a), dy - 72 * s * math.sin(a)),
            ],
            fill=255,
            width=round(4 * s),
        )
    d.line([(dx, dy), (dx + 50 * s, dy - 34 * s)], fill=255, width=round(6 * s))
    _fill(layer, marks, (236, 150, 60), 0.1)
    knobs, d = _shape(layer)
    for kx in (dx - 54 * s, dx + 54 * s):
        d.ellipse((kx - 30 * s, base - 110 * s, kx + 30 * s, base - 50 * s), fill=255)
    _fill(layer, knobs, (60, 54, 50), 0.4)


def books(layer: Image.Image, cx: float, base: float, s: float) -> None:
    spines = [(560, 86, (154, 52, 48), 10), (500, 70, (40, 78, 120), -24), (540, 96, (206, 164, 62), 16),
              (440, 62, (62, 110, 82), -8), (480, 78, (96, 70, 110), 30)]  # fmt: skip
    y = base
    for width, height, color, shift in spines:
        x0, x1 = cx - width / 2 * s + shift * s, cx + width / 2 * s + shift * s
        cover, d = _shape(layer)
        d.rounded_rectangle((x0, y - height * s, x1, y), radius=8 * s, fill=255)
        _fill(layer, cover, color, 0.3)
        pages, d = _shape(layer)
        d.rectangle((x1 - 150 * s, y - (height - 12) * s, x1 - 6 * s, y - 12 * s), fill=255)
        _fill(layer, pages, (236, 228, 208), 0.12)
        band, d = _shape(layer)
        d.rectangle((x0 + 60 * s, y - height * s, x0 + 76 * s, y), fill=255)
        d.rectangle((x0 + 130 * s, y - (height * 0.62) * s, x0 + 300 * s, y - (height * 0.4) * s), fill=255)
        _fill(layer, band, _mix(color, (255, 240, 200), 0.6), 0.1)
        y -= height * s


def game(layer: Image.Image, cx: float, base: float, s: float) -> None:
    w, h, lift = 640 * s, 330 * s, 90 * s
    x0 = cx - w / 2
    top, d = _shape(layer)
    d.polygon(
        [(x0, base - h), (x0 + 70 * s, base - h - lift), (x0 + w + 70 * s, base - h - lift), (x0 + w, base - h)],
        fill=255,
    )
    _fill(layer, top, (196, 60, 52), 0.2)
    side, d = _shape(layer)
    d.polygon(
        [(x0 + w, base - h), (x0 + w + 70 * s, base - h - lift), (x0 + w + 70 * s, base - lift), (x0 + w, base)],
        fill=255,
    )
    _fill(layer, side, (128, 34, 30), 0.3)
    front, d = _shape(layer)
    d.rectangle((x0, base - h, x0 + w, base), fill=255)
    _fill(layer, front, (176, 44, 40), 0.28)
    art, d = _shape(layer)
    d.ellipse((x0 + 60 * s, base - h + 60 * s, x0 + 270 * s, base - 60 * s), fill=255)
    _fill(layer, art, (240, 196, 70), 0.2)
    lines, d = _shape(layer)
    for i, length in enumerate((250, 190, 220)):
        d.rounded_rectangle(
            (x0 + 320 * s, base - h + (90 + i * 62) * s, x0 + (320 + length) * s, base - h + (122 + i * 62) * s),
            radius=10 * s,
            fill=255,
        )
    _fill(layer, lines, (246, 236, 214), 0.08)
    pips, d = _shape(layer)
    for px, py in ((125, 125), (205, 125), (165, 165), (125, 205), (205, 205)):
        d.ellipse(
            (x0 + (px - 14) * s, base - h + (py - 14) * s, x0 + (px + 14) * s, base - h + (py + 14) * s), fill=255
        )
    _fill(layer, pips, (120, 34, 30), 0.1)


def _mug(layer: Image.Image, cx: float, base: float, s: float) -> None:
    handle, d = _shape(layer)
    d.ellipse((cx + 40 * s, base - 150 * s, cx + 130 * s, base - 40 * s), outline=255, width=round(20 * s))
    _fill(layer, handle, (214, 208, 198), 0.25)
    body, d = _shape(layer)
    d.rounded_rectangle((cx - 80 * s, base - 190 * s, cx + 80 * s, base), radius=18 * s, fill=255)
    _fill(layer, body, (224, 218, 208), 0.3)


def room(wall: Color, table: Color, horizon: float) -> Image.Image:
    """A wall and a wooden table top, a little grainy like a phone photo."""
    w, h = W * SS, H * SS
    edge = round(h * horizon)
    scene = Image.new("RGB", (w, h), wall)
    falloff = Image.radial_gradient("L").resize((w * 2, h * 2)).crop((w // 3, h // 4, w // 3 + w, h // 4 + h))
    scene = Image.composite(
        Image.new("RGB", (w, h), _mix(wall, (0, 0, 0), 0.22)), scene, falloff.point(lambda v: v // 2)
    )
    top = Image.new("RGB", (w, h - edge), table)
    d = ImageDraw.Draw(top)
    for i in range(1, 7):
        y = round((h - edge) * (i / 7) ** 1.6)
        d.line([(0, y), (w, y)], fill=_mix(table, (0, 0, 0), 0.22), width=3 * SS)
    depth = Image.linear_gradient("L").resize(top.size).point(lambda v: 90 - v // 3)
    top = Image.composite(Image.new("RGB", top.size, _mix(table, (0, 0, 0), 0.5)), top, depth)
    scene.paste(top, (0, edge))
    grain = Image.effect_noise((w // 2, h // 2), 26).resize((w, h))
    return Image.blend(scene, Image.merge("RGB", (grain, grain, grain)), 0.06)


def photograph(
    draw: Draw, wall: Color, table: Color, *, scale: float, shift: float, clutter: bool
) -> tuple[Image.Image, Image.Image]:
    """The drawn photo and the outline of the item in it."""
    w, h = W * SS, H * SS
    horizon = 0.6
    cx, base = w * (0.5 + shift), h * (horizon + 0.2)
    scene = room(wall, table, horizon)
    things = Image.new("RGBA", (w, h))
    if clutter:
        _mug(things, w * 0.14, h * (horizon + 0.1), SS * 0.9)
    item = Image.new("RGBA", (w, h))
    draw(item, cx, base, SS * scale)
    outline = item.getchannel("A")
    for layer in (things, item):
        alpha = layer.getchannel("A")
        box = alpha.getbbox()
        if not box:
            continue
        # Where something stands, the table is darker.
        ground = Image.new("L", (w, h), 0)
        ImageDraw.Draw(ground).ellipse((box[0] - 20, box[3] - 40, box[2] + 90, box[3] + 46), fill=150)
        scene.paste((30, 22, 16), mask=ground.filter(ImageFilter.GaussianBlur(26 * SS)))
        scene.paste(layer, mask=alpha)
    small = (W, H)
    return scene.resize(small, Image.Resampling.LANCZOS), outline.resize(small, Image.Resampling.LANCZOS)


# -- the items -------------------------------------------------------------------

WOOD, OAK, PINE = (150, 108, 70), (176, 138, 96), (196, 164, 118)
WARM, COOL, SAND = (226, 218, 204), (206, 214, 216), (232, 222, 200)

ITEMS: list[dict[str, Any]] = [
    {
        "keywords": "vase keramik türkis",
        "draw": vase,
        "room": (WARM, WOOD),
        "look": "studio",
        "state": "online",
        "listed": ["kleinanzeigen", "ebay"],
        "days": 3,
        "data": {
            "title": "Keramikvase türkis, handglasiert, 28 cm",
            "description": "Bauchige Vase aus Keramik in kräftigem Türkis. Die Glasur ist glänzend und "
            "rundum unbeschädigt, keine Abplatzer am Rand. Steht sicher und ist innen dicht, also auch "
            "für frische Blumen geeignet.",
            "facts": ["Höhe ca. 28 cm", "Durchmesser ca. 20 cm", "Keramik, glasiert", "innen dicht"],
            "category": "Haus & Garten > Dekoration",
            "brand": "",
            "model": "",
            "size": "28 cm",
            "color": "türkis",
            "material": "Keramik",
            "condition": "very_good",
            "defects": [],
            "price": 18,
            "price_min": 12,
            "price_max": 25,
            "price_reason": "Ohne Marke, aber makellos und in einer gefragten Farbe. Vergleichbare Vasen "
            "dieser Größe liegen zwischen 12 und 25 €.",
            "shipping": "parcel_s",
            "search_terms": ["Vase", "Keramik", "Türkis", "Blumenvase", "Deko"],
            "to_check": ["Höhe nachmessen", "Stempel unter dem Boden?"],
        },
    },
    {
        "keywords": "schreibtischlampe grün messing",
        "draw": lamp,
        "room": (COOL, OAK),
        "look": "studio",
        "state": "draft",
        "days": 0,
        "data": {
            "title": "Schreibtischlampe Gelenkarm, grün mit Messing",
            "description": "Klassische Gelenkarmlampe mit grün lackiertem Schirm und Arm in Messingoptik. "
            "Beide Gelenke lassen sich verstellen und halten ihre Position. Schalter am Kabel.",
            "facts": ["Höhe ca. 50 cm", "Fassung E27", "Arm zweifach verstellbar", "Kabel ca. 1,5 m"],
            "category": "Haus & Garten > Lampen & Licht",
            "brand": "",
            "model": "",
            "size": "50 cm",
            "color": "grün",
            "material": "Metall",
            "condition": "good",
            "defects": ["leichte Kratzer am Fuß"],
            "price": 25,
            "price_min": 18,
            "price_max": 35,
            "price_reason": "Zeitloses Modell in gutem Zustand; die Kratzer am Fuß drücken den Preis etwas.",
            "shipping": "parcel_m",
            "search_terms": ["Schreibtischlampe", "Gelenkarm", "Bürolampe", "Messing", "Vintage"],
            "to_check": ["Leuchtmittel dabei?", "Fassung prüfen: E27 oder E14"],
        },
    },
    {
        "keywords": "gummistiefel kinder gelb 28",
        "draw": boots,
        "room": (SAND, PINE),
        "look": "white",
        "state": "online",
        "listed": ["vinted", "kleinanzeigen"],
        "days": 6,
        "data": {
            "title": "Gummistiefel Kinder gelb Gr. 28",
            "description": "Gelbe Gummistiefel für Kinder, eine Saison getragen. Sohle mit gutem Profil, "
            "innen sauber und trocken gelagert. Dicht, keine Risse.",
            "facts": ["Größe 28", "Naturkautschuk", "Profil gut erhalten", "gefüttert"],
            "category": "Familie, Kind & Baby > Kinderschuhe",
            "brand": "",
            "model": "",
            "size": "28",
            "color": "gelb",
            "material": "Gummi",
            "condition": "good",
            "defects": ["leichte Gebrauchsspuren an den Spitzen"],
            "price": 9,
            "price_min": 6,
            "price_max": 12,
            "price_reason": "Kinderstiefel ohne Marke werden günstig gehandelt; guter Zustand, gängige Größe.",
            "shipping": "parcel_s",
            "search_terms": ["Gummistiefel", "Regenstiefel", "Kinder", "Größe 28", "gelb"],
            "to_check": ["Größe im Schaft nachlesen"],
        },
    },
    {
        "keywords": "radio holz retro",
        "draw": radio,
        "room": (WARM, OAK),
        "look": "studio",
        "state": "sold",
        "sold": (42, "kleinanzeigen"),
        "days": 12,
        "data": {
            "title": "Retro-Radio im Holzgehäuse, UKW/MW",
            "description": "Kofferradio im Holzgehäuse mit cremefarbener Front und großer Senderskala. "
            "Empfang auf UKW und Mittelwelle, Klang warm und kräftig. Läuft am Netz.",
            "facts": ["UKW und MW", "Holzgehäuse", "Teleskopantenne", "Netzbetrieb"],
            "category": "Elektronik > Audio & Hifi",
            "brand": "",
            "model": "",
            "size": "",
            "color": "braun",
            "material": "Holz",
            "condition": "good",
            "defects": [],
            "price": 45,
            "price_min": 30,
            "price_max": 60,
            "price_reason": "Funktionierende Geräte im Holzgehäuse sind gefragt; ohne Marke mittlerer Bereich.",
            "shipping": "parcel_m",
            "search_terms": ["Radio", "Retro", "Vintage", "Holzgehäuse", "Kofferradio"],
            "to_check": ["Hersteller auf der Rückseite?"],
        },
    },
    {
        "keywords": "bücher paket romane",
        "draw": books,
        "room": (COOL, WOOD),
        "look": "original",
        "state": "sold",
        "sold": (12, "private"),
        "days": 20,
        "data": {
            "title": "Bücherpaket: 5 Romane, gebunden",
            "description": "Fünf gebundene Romane aus einem Nichtraucherhaushalt, alle einmal gelesen. "
            "Seiten sauber, Einbände ohne Knicke.",
            "facts": ["5 Bücher", "gebunden", "Nichtraucherhaushalt"],
            "category": "Musik, Filme & Bücher > Bücher",
            "brand": "",
            "model": "",
            "size": "",
            "color": "",
            "material": "",
            "condition": "very_good",
            "defects": [],
            "price": 12,
            "price_min": 8,
            "price_max": 15,
            "price_reason": "Als Paket günstiger als einzeln, dafür schnell verkauft.",
            "shipping": "parcel_s",
            "search_terms": ["Bücher", "Romane", "Bücherpaket", "gebunden"],
            "to_check": ["Titel in die Beschreibung schreiben"],
        },
    },
    {
        "keywords": "brettspiel familie vollständig",
        "draw": game,
        "room": (SAND, WOOD),
        "look": "studio",
        "state": "draft",
        "days": 1,
        "data": {
            "title": "Familien-Brettspiel, vollständig, ab 8 Jahren",
            "description": "Würfelspiel für zwei bis sechs Personen. Alle Teile nachgezählt und vollständig, "
            "Anleitung liegt bei. Der Karton hat an einer Ecke eine kleine Druckstelle.",
            "facts": ["2 bis 6 Spieler", "ab 8 Jahren", "vollständig", "mit Anleitung"],
            "category": "Freizeit, Hobby & Nachbarschaft > Spiele",
            "brand": "",
            "model": "",
            "size": "",
            "color": "rot",
            "material": "",
            "condition": "good",
            "defects": ["Druckstelle an einer Kartonecke"],
            "price": 14,
            "price_min": 10,
            "price_max": 18,
            "price_reason": "Vollständige Spiele mit Anleitung verkaufen sich gut; der Karton kostet ein paar Euro.",
            "shipping": "parcel_m",
            "search_terms": ["Brettspiel", "Gesellschaftsspiel", "Familienspiel", "Würfelspiel"],
            "to_check": ["Name des Spiels in den Titel"],
        },
    },
]


class DemoProvider:
    """Answers with the listing it was given: revising in the demo changes
    nothing, but it does not fail either."""

    name = "demo"

    def __init__(self, db: DB) -> None:
        self.db = db

    def ask(self, prompt: str, *, system: str, schema: dict, images: list, model: str = "") -> Answer:
        if "photos" in schema.get("properties", {}):
            return Answer({"photos": []}, "demo")
        for item in ITEMS:
            if item["data"]["title"] in prompt or item["keywords"] in prompt:
                return Answer(dict(item["data"]), "demo")
        return Answer(dict(ITEMS[0]["data"]), "demo")


def seed(settings: Settings) -> None:
    db = DB(settings.db_path)
    Auth(db, SETUP_CODE).setup(SETUP_CODE, PASSWORD)
    # A provider that needs no key, so the app does not ask for one. It is
    # never called: the worker below answers from this file.
    db.save_settings({"location": "12345 Musterstadt", "provider": "ollama", "model": "demo"})
    editor = imaging.Editor("demo", settings.model_dir)
    today = datetime.now().astimezone()
    for spec in ITEMS:
        item_id = db.add_item(spec["keywords"], "")
        wall, table = spec["room"]
        for scale, shift, clutter in ((1.0, 0.0, True), (1.3, 0.06, False)):
            photo, outline = photograph(spec["draw"], wall, table, scale=scale, shift=shift, clutter=clutter)
            name = imaging.store(photo, settings.photo_dir)
            # The outline is known from the drawing; with it in place the
            # editor never asks for a model.
            outline.save(imaging.paths(settings.photo_dir, name)["mask"])
            photo_id = db.add_photo(item_id, name, spec["look"])
            if spec["look"] != "original":
                editor.produce(settings.photo_dir, name, spec["look"])
                db.set_photo_state(photo_id, "done")
        db.save_draft(item_id, {**spec["data"], "_model": "demo"})
        for platform in spec.get("listed", []):
            db.set_listed(item_id, platform, "")
        if "sold" in spec:
            db.mark_sold(item_id, *spec["sold"])
        # Spread over the last weeks, so the list and the statistics have
        # something to show.
        created = (today - timedelta(days=spec["days"], hours=3)).isoformat(timespec="seconds")
        sold_at = (today - timedelta(days=max(0, spec["days"] - 4))).isoformat(timespec="seconds")
        with db.lock:
            db.con.execute("UPDATE item SET created=?, updated=? WHERE id=?", (created, created, item_id))
            db.con.execute("UPDATE item SET sold_at=? WHERE id=? AND sold_at IS NOT NULL", (sold_at, item_id))
            db.con.execute("UPDATE listing SET since=? WHERE item_id=?", (created, item_id))
    db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default="demo-data", help="created and filled if it does not exist yet")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--seed-only", action="store_true", help="fill the directory and stop")
    args = parser.parse_args()

    settings = replace(Settings(), data_dir=Path(args.data_dir), host=args.host, port=args.port, cutout=True)
    if not settings.db_path.exists():
        print(f"Drawing the demo items into {settings.data_dir} ...", flush=True)
        seed(settings)
    print(f"\n  Demo password:  {PASSWORD}\n", flush=True)
    if args.seed_only:
        return 0

    import uvicorn

    from troedel.web.app import create_app

    db = DB(settings.db_path)
    provider = DemoProvider(db)
    worker = Worker(db, settings, markets.get(), lambda: provider, imaging.Editor("demo", settings.model_dir))
    uvicorn.run(create_app(settings, worker=worker), host=settings.host, port=settings.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
