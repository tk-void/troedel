"""Settings that are fixed for the lifetime of the process.

They come from the environment, because that is what a container or a
service unit can set. Everything a person changes while using the app
(texts, default look, AI provider) lives in the database instead; see
``db.DEFAULT_SETTINGS``.

Secrets are never read from a variable alone: ``TROEDEL_API_KEY_FILE`` points
to a file, so that the key can be mounted as a secret and does not show up in
``docker inspect``. ``TROEDEL_API_KEY`` exists for quick local runs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PREFIX = "TROEDEL_"
TRUE = {"1", "true", "yes", "on"}
FALSE = {"0", "false", "no", "off"}


class ConfigError(ValueError):
    pass


def _flag(env: dict[str, str], name: str, default: bool | None) -> bool | None:
    raw = env.get(PREFIX + name, "").strip().lower()
    if not raw:
        return default
    if raw in TRUE:
        return True
    if raw in FALSE:
        return False
    raise ConfigError(f"{PREFIX}{name} must be one of true/false, got {raw!r}")


def _number(env: dict[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = env.get(PREFIX + name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{PREFIX}{name} must be a number, got {raw!r}") from exc
    if not low <= value <= high:
        raise ConfigError(f"{PREFIX}{name} must be between {low} and {high}")
    return value


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    host: str = "127.0.0.1"
    """Loopback unless told otherwise: reaching the app from a phone is a
    decision, not a default."""
    port: int = 8099
    trust_proxy: bool = False
    """Believe ``X-Forwarded-Proto`` and ``X-Forwarded-For``. Only correct
    behind a reverse proxy that sets them; otherwise any client could claim
    to be someone else and dodge the login throttle."""

    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    """Provider settings from the environment win over the ones stored in
    the app and lock them there."""

    cutout: bool | None = None
    """None means: on if the ``cutout`` extra is installed."""
    cutout_model: str = "birefnet-general-lite"
    max_photos: int = 12
    analysis_photos: int = 4
    """How many photos of an item the model gets to see. More costs more and
    rarely changes the text."""
    setup_code: str = field(default="", repr=False)
    """Fixes the one-time setup code instead of printing a random one, for
    unattended installs."""

    @property
    def photo_dir(self) -> Path:
        return self.data_dir / "photos"

    @property
    def model_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "troedel.db"

    @property
    def secrets_path(self) -> Path:
        return self.data_dir / "secrets.json"


def load(env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ if env is None else env)

    def text(name: str, default: str = "") -> str:
        return env.get(PREFIX + name, default).strip()

    api_key = text("API_KEY")
    key_file = text("API_KEY_FILE")
    if key_file:
        try:
            api_key = Path(key_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigError(f"{PREFIX}API_KEY_FILE: cannot read {key_file}: {exc.strerror}") from exc

    return Settings(
        data_dir=Path(text("DATA_DIR", "data")).expanduser(),
        host=text("HOST", "127.0.0.1"),
        port=_number(env, "PORT", 8099, 1, 65535),
        trust_proxy=bool(_flag(env, "TRUST_PROXY", False)),
        provider=text("PROVIDER"),
        model=text("MODEL"),
        base_url=text("BASE_URL"),
        api_key=api_key,
        cutout=_flag(env, "CUTOUT", None),
        cutout_model=text("CUTOUT_MODEL", "birefnet-general-lite"),
        max_photos=_number(env, "MAX_PHOTOS", 12, 1, 40),
        analysis_photos=_number(env, "ANALYSIS_PHOTOS", 4, 1, 12),
        setup_code=text("SETUP_CODE"),
    )
