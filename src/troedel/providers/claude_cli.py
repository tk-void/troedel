"""Claude through the ``claude`` command line tool that is already installed
and signed in on this machine.

**Experimental.** Trödel starts the unmodified program once per request and
never sees, stores or forwards a credential; whatever account the program is
signed in with is the account that is used and billed. Whether your plan's
terms cover calling it from another program like this is for you to check
with Anthropic. Anthropic's guidance for products is to use an API key, and
future versions of the tool may stop using a subscription sign-in in
non-interactive mode, at which point this provider needs an API key too and
has no advantage over the ``anthropic`` one.

The model gets no tools at all: no shell, no file access, no network, no
settings or hooks from disk. It reads the photos from the request and
returns JSON.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .base import Answer, Image, ProviderError, ProviderNotConfigured, ProviderUnavailable, Schema, checked, strict

DEFAULT_MODEL = "opus"
MODELS = {"opus": "Opus", "sonnet": "Sonnet", "haiku": "Haiku"}

SWITCHES = [
    "-p",
    "--tools",
    "",
    "--strict-mcp-config",
    "--setting-sources",
    "",
    "--disable-slash-commands",
    "--no-session-persistence",
    "--input-format",
    "stream-json",
    "--output-format",
    "stream-json",
    "--verbose",
]
"""The boundary is in these switches, not in the prompt. ``stream-json`` in
is what lets photos travel as content blocks; it requires the same format
out, which requires ``--verbose``."""

KEPT = ("USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT", "PATHEXT", "USER", "LOGNAME")
"""What the program gets from the environment besides PATH and HOME. On
Windows it finds its sign-in through these and does not start without
SYSTEMROOT; on macOS the keychain wants the user name."""


def usual_places() -> list[Path]:
    """Where the program and the ``node`` it may need get installed.

    A program started from the Finder, the Dock or the Start menu does not
    get the PATH of a terminal: on macOS that is ``/usr/bin:/bin:/usr/sbin:
    /sbin``, so ``claude`` was reported missing in the window although it
    ran fine in a shell."""
    home = Path.home()
    places = [home / ".local" / "bin", home / ".claude" / "local", home / ".npm-global" / "bin"]
    if sys.platform == "win32":
        if os.environ.get("APPDATA"):
            places.append(Path(os.environ["APPDATA"]) / "npm")
    else:
        places += [Path("/opt/homebrew/bin"), Path("/usr/local/bin")]
    return places


def search_path() -> str:
    """PATH, followed by the usual places that are not on it."""
    parts = [part for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    parts += [str(place) for place in usual_places() if str(place) not in parts and place.is_dir()]
    return os.pathsep.join(parts)


LIMIT_HINTS = ("usage limit", "rate limit", "limit reached", "quota", "overloaded")


class ClaudeCliProvider:
    name = "claude-cli"

    def __init__(self, model: str = "", binary: str = "claude", timeout: float = 240.0) -> None:
        self.model = model or DEFAULT_MODEL
        self.path = search_path()
        self.binary = shutil.which(binary, path=self.path) or ""
        if not self.binary:
            raise ProviderNotConfigured(f"{binary!r} is not installed or not on PATH", "cli")
        self.timeout = timeout

    def command(self, model: str, system: str, schema: Schema) -> list[str]:
        return [
            self.binary,
            *SWITCHES,
            "--model",
            model,
            "--system-prompt",
            system,
            "--json-schema",
            json.dumps(strict(schema), ensure_ascii=False),
        ]

    @staticmethod
    def message(prompt: str, images: list[Image]) -> bytes:
        content: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image.media_type,
                    "data": base64.standard_b64encode(image.data).decode("ascii"),
                },
            }
            for image in images
        ]
        content.append({"type": "text", "text": prompt})
        return (json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + "\n").encode()

    def ask(self, prompt: str, *, system: str, schema: Schema, images: list[Image], model: str = "") -> Answer:
        model = model or self.model
        # An empty directory per call: even if a tool were available, there
        # would be nothing here to read.
        with tempfile.TemporaryDirectory(prefix="troedel-ask-") as workdir:
            env = {
                # The same PATH the program was found on: installed through
                # npm it is a script that needs ``node`` from there.
                "PATH": self.path,
                "HOME": os.environ.get("HOME", workdir),
                "LANG": "C.UTF-8",
                "DISABLE_AUTOUPDATER": "1",
                **{name: os.environ[name] for name in KEPT if name in os.environ},
            }
            try:
                # The prompt goes in on stdin: it does not show up in the
                # process list and has no length limit.
                done = subprocess.run(
                    self.command(model, system, schema),
                    input=self.message(prompt, images),
                    capture_output=True,
                    cwd=workdir,
                    env=env,
                    timeout=self.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ProviderUnavailable(f"claude did not answer within {self.timeout:.0f} s") from exc
            except OSError as exc:
                raise ProviderNotConfigured(f"cannot start claude: {exc}") from exc
        return self.read(
            done.stdout.decode("utf-8", "replace"),
            done.stderr.decode("utf-8", "replace"),
            done.returncode,
            schema,
            model,
        )

    @staticmethod
    def read(stdout: str, stderr: str, returncode: int, schema: Schema, model: str) -> Answer:
        result = None
        for line in reversed(stdout.splitlines()):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("type") == "result":
                result = event
                break
        if result is None:
            detail = (stderr.strip() or stdout.strip())[:300]
            if any(hint in detail.lower() for hint in LIMIT_HINTS):
                raise ProviderUnavailable(detail)
            raise ProviderError(f"claude ended with {returncode}: {detail}")
        text = str(result.get("result") or "")
        if result.get("is_error") or result.get("subtype") not in (None, "success"):
            detail = f"{result.get('subtype')}: {text[:300]}"
            if result.get("api_error_status") == 429 or any(h in text.lower() for h in LIMIT_HINTS):
                raise ProviderUnavailable(detail)
            if "login" in text.lower() or "authenticat" in text.lower():
                raise ProviderError("claude is not signed in on this machine", "signin")
            raise ProviderError(detail)
        data = result.get("structured_output")
        if not isinstance(data, dict):
            raise ProviderError("claude returned no structured answer", "invalid")
        used = list(result.get("modelUsage") or {})
        return Answer(checked(data, schema), used[-1] if used else model)
