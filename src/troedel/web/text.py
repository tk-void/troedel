"""German interface text that is produced in Python.

The interface is German only for now. Its text lives in three places: the
templates, the ``STRINGS`` table at the top of ``static/troedel.js``, and
this module. A second language means moving those into catalogues; the
names here are already keys, not sentences, to make that step small.
"""

from __future__ import annotations

from datetime import datetime

STATUS = {
    "queued": "In der Warteschlange",
    "writing": "Wird geschrieben …",
    "revising": "Wird angepasst …",
    "failed": "Fehler",
    "draft": "Entwurf",
    "online": "Online",
    "sold": "Verkauft",
    "archived": "Archiviert",
}
FILTERS = {
    "all": ("Alle", ("queued", "writing", "revising", "failed", "draft", "online", "sold")),
    "drafts": ("Entwürfe", ("queued", "writing", "revising", "failed", "draft")),
    "online": ("Online", ("online",)),
    "sold": ("Verkauft", ("sold",)),
    "archived": ("Archiv", ("archived",)),
}
LOOKS = {"studio": "Studio", "white": "Weiß", "tidy": "Aufgeräumt", "original": "Original"}
LOOK_HINTS = {
    "studio": "Freigestellt, heller Grund, weicher Schatten",
    "white": "Freigestellt auf Weiß",
    "tidy": "Originalfoto, Störendes wegretuschiert",
    "original": "Unbearbeitet",
}
FIELDS = {
    "title": "Titel",
    "price": "Preis",
    "condition": "Zustand",
    "description": "Beschreibung",
    "facts": "Fakten",
    "brand": "Marke",
    "size": "Größe",
    "color": "Farbe",
    "material": "Material",
    "model": "Modell",
    "category": "Kategorie",
    "shipping": "Versand",
    "defects": "Mängel",
}
PROVIDERS = {
    "anthropic": ("Claude (Anthropic-API)", "API-Schlüssel von console.anthropic.com. Abrechnung nach Verbrauch."),
    "gemini": (
        "Gemini (Google)",
        "API-Schlüssel von aistudio.google.com. Es gibt ein kostenloses Kontingent – "
        "dort darf Google die Fotos und Texte zur Verbesserung seiner Produkte nutzen.",
    ),
    "openai": ("OpenAI", "API-Schlüssel von platform.openai.com. Das Modell muss Bilder lesen können."),
    "ollama": (
        "Ollama (lokal)",
        "Läuft auf dem eigenen Rechner, die Fotos verlassen ihn nicht. Braucht ein Modell, das Bilder lesen kann.",
    ),
    "custom": (
        "Anderer Dienst (OpenAI-kompatibel)",
        "Jede Adresse, die das Chat-Completions-Protokoll spricht, etwa OpenRouter oder LM Studio.",
    ),
    "claude-cli": (
        "Claude Code (experimentell, nicht im Container)",
        "Nutzt das Programm „claude“, das auf demselben Rechner wie Trödel installiert und angemeldet ist. "
        "Läuft Trödel in einem Docker-Container, geht dieser Weg nicht: dort gibt es das Programm nicht. "
        "Ob dein Tarif diese Nutzung abdeckt, klärst du mit Anthropic; der Weg kann jederzeit wegfallen.",
    ),
}
ERRORS = {
    "unavailable": "Der KI-Dienst ist gerade ausgeschöpft oder nicht erreichbar. Später erneut versuchen.",
    "not_configured": "Es ist noch kein KI-Anbieter eingerichtet. Das geht in den Einstellungen.",
    "auth": "Der KI-Dienst hat den Zugang abgelehnt. Bitte den Schlüssel in den Einstellungen prüfen.",
    "signin": "Das Programm „claude“ ist auf diesem Rechner nicht angemeldet. Einmal im Terminal „claude“ starten "
    "und dort anmelden, dann erneut versuchen.",
    "model": "Der KI-Dienst kennt das eingestellte Modell nicht. Bitte in den Einstellungen prüfen.",
    "declined": "Der KI-Dienst hat die Anfrage zu diesen Fotos abgelehnt.",
    "invalid": "Die Antwort des KI-Dienstes war unbrauchbar. Bitte erneut versuchen.",
    "failed": "Das hat nicht geklappt.",
}
MISSING = {
    "provider": "",
    "api_key": "Es fehlt noch der API-Schlüssel.",
    "model": "Es fehlt noch der Name des Modells.",
    "base_url": "Es fehlt noch die Adresse des Dienstes.",
    "cli": "Das Programm „claude“ ist dort, wo Trödel läuft, nicht installiert. In einem Docker-Container gibt es "
    "es nicht: Trödel dafür ohne Container starten oder einen Anbieter mit API-Schlüssel wählen.",
}
"""Why the chosen provider cannot be used yet, by ``ProviderNotConfigured.missing``."""
PASSWORD = {
    "password_too_short": "Das Passwort braucht mindestens {min} Zeichen.",
    "password_too_long": "Das Passwort ist zu lang.",
}
API = {
    "not_found": "Artikel nicht gefunden",
    "busy": "Wird gerade bearbeitet",
    "need_photo": "Mindestens ein Foto",
    "too_many_photos": "Höchstens {n} Fotos je Artikel",
    "photo_too_large": "Ein Foto ist zu groß (höchstens {mb} MB)",
    "not_an_image": "Das ist kein lesbares Bild",
    "unknown_field": "Unbekanntes Feld „{field}“",
    "price_number": "Preis bitte als ganze Zahl",
    "amount_number": "Betrag bitte als Zahl",
    "bad_state": "Status nicht erlaubt",
    "bad_choice": "Auswahl nicht erlaubt",
    "unknown_platform": "Unbekannte Plattform",
    "link_scheme": "Link bitte mit https://",
    "nothing_to_revise": "Noch keine Anzeige zum Anpassen",
    "what_to_change": "Was soll anders werden?",
    "nothing_to_undo": "Nichts rückgängig zu machen",
    "last_photo": "Das letzte Foto bleibt",
    "not_edited_yet": "Noch nicht bearbeitet",
    "editing_off": "Bildbearbeitung ist nicht installiert",
    "login_required": "Bitte anmelden",
    "forbidden": "Anfrage abgelehnt",
    "helper_off": "Die Ausfüllhilfe ist ausgeschaltet",
}
MONTHS = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]
MONTHS_SHORT = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
MONTHS_DATE = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sept.", "Okt.", "Nov.", "Dez."]


def date(iso: str | None) -> str:
    try:
        d = datetime.fromisoformat(iso or "")
    except ValueError:
        return ""
    if d.date() == datetime.now(d.tzinfo).date():
        return f"heute, {d:%H:%M}"
    return f"{d.day}. {MONTHS_DATE[d.month - 1]}"


def model_name(identifier: str) -> str:
    """claude-opus-5-5 -> Opus 5.5; anything else is shown as it is."""
    if not identifier.startswith("claude-"):
        return identifier
    parts = identifier.removeprefix("claude-").split("-")
    digits = [p for p in parts[1:] if p.isdigit() and len(p) < 4]
    return parts[0].capitalize() + (" " + ".".join(digits) if digits else "")


def pieces(n: int) -> str:
    return f"{n} {'Teil' if n == 1 else 'Teile'}"
