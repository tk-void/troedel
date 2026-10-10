"""The API key someone types into the settings.

It is kept in its own file inside the data directory, readable by the
owner only, and not in the database: a copy of the database handed to
someone for debugging, or an export, must not carry a credential. Nothing in
the app ever sends the key back to a browser.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


class SecretsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def get(self, name: str) -> str:
        return self._read().get(name, "")

    def set(self, name: str, value: str) -> None:
        data = self._read()
        if value:
            data[name] = value
        else:
            data.pop(name, None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Created with the final mode, so the key is never on disk in a
        # file others can read, not even for a moment.
        temp = self.path.with_suffix(".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out)
        os.chmod(temp, 0o600)
        temp.replace(self.path)

    @staticmethod
    def hint(value: str) -> str:
        """Enough to recognise a key, not enough to use it."""
        return f"…{value[-4:]}" if len(value) >= 12 else ("gesetzt" if value else "")
