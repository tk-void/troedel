"""A market is a country's second-hand world: the language listings are
written in, the currency, the platforms and what they call things.

It is separate from the language of the interface (``locales/``). Germany is
the only market so far. Adding one means adding a module here with the same
names as ``de``; nothing else in the app knows German.
"""

from __future__ import annotations

from types import ModuleType

from . import de

MARKETS: dict[str, ModuleType] = {"de": de}
DEFAULT = "de"


def get(code: str = DEFAULT) -> ModuleType:
    return MARKETS.get(code, MARKETS[DEFAULT])
