"""Germany: Kleinanzeigen, Vinted, eBay, Facebook Marketplace.

Everything in German in this file is content: prompts for the model, words
that end up in a listing, and the vocabulary of the platforms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NAME = "Deutschland"
CURRENCY = "€"

CONDITIONS = {
    "new_with_tags": "Neu mit Etikett",
    "new": "Neu",
    "very_good": "Sehr gut",
    "good": "Gut",
    "fair": "In Ordnung",
    "defective": "Defekt",
}
SHIPPING = {
    "small": "Päckchen",
    "parcel_s": "Paket S",
    "parcel_m": "Paket M",
    "parcel_l": "Paket L",
    "pickup": "Nur Abholung",
}

DEFAULT_TEXTS = {
    "pickup": "Abholung möglich",
    "shipping": "Versand gegen Aufpreis möglich",
    "footer": "Privatverkauf, daher keine Garantie und keine Rücknahme.",
}
"""What the settings start with. Private sellers in Germany customarily
exclude warranty and returns in the listing."""

# -- prompts --------------------------------------------------------------------

SYSTEM = """\
Du schreibst Verkaufsanzeigen für private Gebrauchtverkäufe in Deutschland \
(Kleinanzeigen, Vinted, eBay). Du bekommst Fotos eines Gegenstands und ein \
kurzes Stichwort des Verkäufers.

Grundsätze:
- Ehrlich, sachlich, freundlich. Kein Werbesprech, keine Superlative, keine \
Emojis, keine Großbuchstaben, keine Ausrufezeichen.
- Was der Verkäufer schreibt, hat Vorrang vor deinem Eindruck vom Foto.
- Erfinde nichts. Marke, Größe, Material, Modell nur, wenn sie auf dem Foto \
lesbar oder im Stichwort genannt sind. Sonst leer lassen und unter \
"to_check" kurz notieren, was der Verkäufer prüfen sollte.
- Sichtbare Gebrauchsspuren und Mängel nennen. Der Zustand ergibt sich aus \
den Fotos und dem Stichwort.
- Personen, Gesichter, Wohnung und Hintergrund nie beschreiben.
- Alle Texte auf Deutsch.

Felder:
- title: höchstens 65 Zeichen. Artikel, Marke und das wichtigste Merkmal \
(z. B. Größe), so wie Käufer suchen. Keine Füllwörter wie "Top" oder "Super".
- description: zwei bis vier kurze, natürliche Sätze in der Ich-Form des \
Verkäufers. Ohne Versand-, Zahlungs- oder Haftungshinweise - die ergänzt die \
App.
- facts: drei bis sechs knappe Fakten (Maße, Größe, Material, Lieferumfang). \
Nur Gesichertes.
- category: passender Kategoriepfad bei Kleinanzeigen, z. B. \
"Familie, Kind & Baby > Kinderschuhe".
- brand, model, size, color, material: nur Gesichertes, sonst leer.
- condition: new_with_tags (neu mit Etikett), new (neu), very_good (sehr \
gut), good (gut), fair (in Ordnung) oder defective (defekt).
- defects: sichtbare Mängel, je einer pro Eintrag. Leer, wenn keine.
- price: realistischer Gebrauchtpreis in ganzen Euro, zu dem sich der \
Artikel privat innerhalb weniger Wochen verkauft. Lieber etwas günstiger. \
price_min und price_max geben die übliche Spanne. price_reason: ein Satz, \
worauf die Schätzung beruht (Neupreis, Marke, Zustand, Nachfrage).
- shipping: die kleinste passende Versandgröße: small (Päckchen), parcel_s, \
parcel_m, parcel_l oder pickup (nur Abholung, bei sperrigen oder sehr \
schweren Dingen).
- search_terms: bis zu acht Begriffe, nach denen Käufer suchen würden.
- to_check: was der Verkäufer prüfen oder ergänzen sollte. Leer, wenn nichts.
"""

REVISE_SYSTEM = (
    SYSTEM
    + """
Jetzt überarbeitest du eine bestehende Anzeige. Der Verkäufer sagt, was \
anders werden soll. Ändere nur das, was die Anweisung verlangt, und alles, \
was daraus zwingend folgt (nennt er eine andere Größe, ändern sich Titel, \
Größe und Fakten). Alle übrigen Felder übernimmst du Wort für Wort - der \
Verkäufer hat sie womöglich schon von Hand korrigiert. Nennt er einen Preis, \
gilt der, auch gegen deine Schätzung.
"""
)

DISTRACTOR_SYSTEM = """\
Du bereitest Fotos für Verkaufsanzeigen vor. Auf jedem Foto ist ein \
Verkaufsgegenstand. Markiere alles, was stört und wegretuschiert werden soll: \
Personen und Körperteile, Haustiere, Poster und Bilder an der Wand, Kabel, \
Müll, andere Gegenstände und Möbel, die nicht zum Verkauf gehören, \
Spiegelungen von Personen.

Nicht markieren: den Verkaufsgegenstand mit allem Zubehör, die Fläche, auf \
der er steht oder liegt (Boden, Tisch, Wiese), und ruhige Flächen wie Wände, \
Türen, Fenster oder Himmel.

Gib je Störer einen eng anliegenden Rahmen in Koordinaten 0 bis 1000 an \
(x0, y0 oben links, x1, y1 unten rechts, bezogen auf Breite und Höhe des \
Fotos). Ein Rahmen darf keinen Teil des Verkaufsgegenstands enthalten - \
lieber einen Störer auslassen als den Gegenstand zu treffen. Ist nichts \
störend, bleibt die Liste leer. "photo" zählt die Fotos ab 1.
"""


def compose_prompt(keywords: str, product: str, note: str, previous: dict[str, Any] | None) -> str:
    parts = [f"Stichwort des Verkäufers: {keywords.strip() or '(keins)'}"]
    if product.strip():
        parts.append(f"Produktname laut Verkäufer: {product.strip()}")
    if previous and previous.get("title"):
        parts.append(
            "Bisheriger Entwurf (der Verkäufer möchte ihn überarbeitet haben):\n"
            f"Titel: {previous.get('title', '')}\n"
            f"Beschreibung: {previous.get('description', '')}\n"
            f"Preis: {previous.get('price', '')} €"
        )
    if note.strip():
        parts.append(f"Zusätzlicher Hinweis des Verkäufers, bitte berücksichtigen: {note.strip()}")
    parts.append("Erstelle die Anzeige zu den Fotos.")
    return "\n\n".join(parts)


def revise_prompt(current_json: str, instruction: str) -> str:
    return f"Bisherige Anzeige als JSON:\n{current_json}\n\nAnweisung des Verkäufers: {instruction.strip()}"


def distractor_prompt(count: int, subject: str) -> str:
    return f"Fotos 1 bis {count} der Reihe nach. Verkaufsgegenstand: {subject.strip() or 'siehe Fotos'}."


# -- platforms ------------------------------------------------------------------


@dataclass
class Field:
    key: str
    """Stable name, used by the fill helper."""
    label: str
    value: str
    long: bool = False
    """Several lines: shown as a block instead of a row."""
    hint: str = ""


@dataclass
class Platform:
    id: str
    name: str
    color: str
    new_listing_url: str
    fields: list[Field] = field(default_factory=list)
    fill_helper: bool = False
    """The userscript knows this platform's form."""

    def value(self, key: str) -> str:
        return next((f.value for f in self.fields if f.key == key), "")


NAMES = {"kleinanzeigen": "Kleinanzeigen", "vinted": "Vinted", "ebay": "eBay", "facebook": "Facebook Marketplace"}
SHORT = {"kleinanzeigen": "KA", "vinted": "Vinted", "ebay": "eBay", "facebook": "FB"}
BADGES = {"kleinanzeigen": "KA", "vinted": "V", "ebay": "eB", "facebook": "FB"}
COLORS = {"kleinanzeigen": "#1d4b00", "vinted": "#007782", "ebay": "#0064d2", "facebook": "#0866ff"}
SOLD_ELSEWHERE = {"private": "Privat"}
"""Ways to sell that are not a platform."""

_CONDITION = {
    "kleinanzeigen": {
        "new_with_tags": "Neu",
        "new": "Neu",
        "very_good": "Sehr gut",
        "good": "Gut",
        "fair": "In Ordnung",
        "defective": "Defekt",
    },
    "vinted": {
        "new_with_tags": "Neu mit Etikett",
        "new": "Neu ohne Etikett",
        "very_good": "Sehr gut",
        "good": "Gut",
        "fair": "Zufriedenstellend",
        "defective": "Zufriedenstellend",
    },
    "ebay": {
        "new_with_tags": "Neu mit Etikett",
        "new": "Neu",
        "very_good": "Gebraucht",
        "good": "Gebraucht",
        "fair": "Gebraucht",
        "defective": "Als Ersatzteil / defekt",
    },
    "facebook": {
        "new_with_tags": "Neu",
        "new": "Neu",
        "very_good": "Gebraucht – wie neu",
        "good": "Gebraucht – gut",
        "fair": "Gebraucht – akzeptabel",
        "defective": "Gebraucht – akzeptabel",
    },
}
_VINTED_PARCEL = {
    "small": "Klein",
    "parcel_s": "Klein",
    "parcel_m": "Mittel",
    "parcel_l": "Groß",
    "pickup": "Groß (oder nur Abholung in der Beschreibung)",
}


def shorten(text: str, length: int) -> str:
    """Cut at a word boundary."""
    text = " ".join(text.split())
    if len(text) <= length:
        return text
    cut = text[: length + 1].rsplit(" ", 1)[0]
    return (cut or text[:length]).rstrip(" ,;:-–")


def money(amount: Any) -> str:
    try:
        return f"{int(amount)} {CURRENCY}"
    except (TypeError, ValueError):
        return ""


def _details(d: dict[str, Any]) -> list[str]:
    """Facts from the single fields that the fact list does not already
    mention."""
    points = [str(p) for p in d.get("facts") or []]
    present = " ".join(points).lower()
    for label, key in (("Marke", "brand"), ("Größe", "size"), ("Farbe", "color"), ("Material", "material")):
        value = str(d.get(key) or "").strip()
        if value and value.lower() not in present:
            points.append(f"{label}: {value}")
    if d.get("condition"):
        points.append(f"Zustand: {CONDITIONS.get(d['condition'], d['condition'])}")
    points += [f"Hinweis: {m}" for m in d.get("defects") or []]
    return points


def description(d: dict[str, Any], s: dict[str, str], *, private: bool, handover: bool) -> str:
    blocks = [str(d.get("description") or "").strip()]
    points = _details(d)
    if points:
        blocks.append("\n".join(f"• {p}" for p in points))
    if handover:
        lines = []
        pickup = s.get("pickup", "").strip()
        if pickup:
            place = s.get("location", "").strip()
            lines.append(f"{pickup} in {place}." if place and place not in pickup else pickup.rstrip(".") + ".")
        if d.get("shipping") != "pickup" and s.get("shipping", "").strip():
            lines.append(s["shipping"].strip().rstrip(".") + ".")
        if lines:
            blocks.append(" ".join(lines))
    if private and s.get("footer", "").strip():
        blocks.append(s["footer"].strip())
    return "\n\n".join(b for b in blocks if b)


def platforms(d: dict[str, Any], s: dict[str, str]) -> list[Platform]:
    """One listing, cut to fit each platform. No second call to the model:
    the fields are there, only lengths, the words for the condition and the
    footer differ."""
    title = str(d.get("title") or "")
    price = money(d.get("price"))
    negotiable = s.get("negotiable") == "1"
    condition = str(d.get("condition") or "")

    def cond(platform: str) -> str:
        return _CONDITION[platform].get(condition, CONDITIONS.get(condition, condition))

    # Step 2 directly: category and form are on one page there.
    ka = Platform(
        "kleinanzeigen",
        NAMES["kleinanzeigen"],
        COLORS["kleinanzeigen"],
        "https://www.kleinanzeigen.de/p-anzeige-aufgeben-schritt2.html",
        fill_helper=True,
    )
    ka.fields = [
        Field("title", "Titel", shorten(title, 65), hint="max. 65 Zeichen"),
        Field("price", "Preis", price, hint="Verhandlungsbasis" if negotiable else "Festpreis"),
        Field("category", "Kategorie", str(d.get("category") or ""), hint="Vorschlag"),
        Field("condition", "Zustand", cond("kleinanzeigen")),
        Field("description", "Beschreibung", description(d, s, private=True, handover=True), long=True),
    ]

    vi = Platform("vinted", NAMES["vinted"], COLORS["vinted"], "https://www.vinted.de/items/new", fill_helper=True)
    vi.fields = [
        Field("title", "Titel", shorten(title, 60)),
        Field("description", "Beschreibung", description(d, s, private=False, handover=False), long=True),
        Field("brand", "Marke", str(d.get("brand") or ""), hint="leer = „Keine Marke“"),
        Field("size", "Größe", str(d.get("size") or "")),
        Field("condition", "Zustand", cond("vinted")),
        Field("color", "Farbe", str(d.get("color") or "")),
        Field("material", "Material", str(d.get("material") or "")),
        Field("price", "Preis", price),
        Field("parcel", "Paketgröße", _VINTED_PARCEL.get(str(d.get("shipping") or ""), "")),
    ]

    # eBay searches by title: the 80 characters are filled up with search
    # terms that are not in it yet.
    eb_title = title
    for term in d.get("search_terms") or []:
        if term.lower() not in eb_title.lower() and len(eb_title) + len(term) + 1 <= 80:
            eb_title = f"{eb_title} {term}"
    eb = Platform("ebay", NAMES["ebay"], COLORS["ebay"], "https://www.ebay.de/sl/sell")
    eb.fields = [
        Field("title", "Titel", shorten(eb_title, 80), hint="max. 80 Zeichen"),
        Field("condition", "Zustand", cond("ebay")),
        Field("price", "Preis", price, hint="Sofort-Kaufen"),
        Field("description", "Beschreibung", description(d, s, private=True, handover=True), long=True),
    ]

    fb = Platform("facebook", NAMES["facebook"], COLORS["facebook"], "https://www.facebook.com/marketplace/create/item")
    fb.fields = [
        Field("title", "Titel", shorten(title, 100)),
        Field("price", "Preis", price),
        Field("condition", "Zustand", cond("facebook")),
        Field("description", "Beschreibung", description(d, s, private=True, handover=True), long=True),
    ]
    return [ka, vi, eb, fb]
