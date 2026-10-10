"""One password in front of everything.

Trödel holds photos from someone's home, so nothing is served without a
login, and there is no way to run it without a password.

* The password is stored as an Argon2id hash.
* First start: the password is set in the browser, but only by someone who
  can read the server's log. The log shows a one-time setup code; without
  it, whoever reaches the port first could claim the instance.
* A login creates a random session token. The browser gets it in a cookie,
  the database keeps only its SHA-256, so a copy of the database does not
  let anyone in.
* Failed attempts are throttled per client and overall.
* The fill helper (a userscript running on the marketplace's page) cannot
  use the cookie. It gets its own token with its own, narrower scope.

What this does not do: encrypt the connection. Over plain HTTP the password
crosses the network readable. See docs/security.md for HTTPS.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .db import DB

MIN_PASSWORD = 10
MAX_PASSWORD = 256
"""Argon2 is deliberately slow; an upper bound keeps a giant "password"
from becoming a way to keep the server busy."""

SESSION_IDLE = timedelta(days=30)
"""A session ends after this long without use."""
SESSION_MAX = timedelta(days=180)
"""... and after this long in any case."""
TOUCH_EVERY = timedelta(minutes=10)

BROWSER = "browser"
HELPER = "helper"

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
"""No 0/O and 1/I: the setup code is read off a log and typed by hand."""

_hasher = PasswordHasher()


class PasswordRejected(ValueError):
    """The chosen password does not meet the rules. ``args[0]`` is a
    message key for the interface."""


def check_password_rules(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise PasswordRejected("password_too_short")
    if len(password) > MAX_PASSWORD:
        raise PasswordRejected("password_too_long")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_setup_code() -> str:
    groups = ["".join(secrets.choice(CODE_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "-".join(groups)


def normalise_code(code: str) -> str:
    return "".join(c for c in code.upper() if c.isalnum())


@dataclass
class _Bucket:
    failures: int = 0
    last: float = 0.0
    blocked_until: float = 0.0


class Throttle:
    """Slows down guessing.

    Per client: five free attempts, then the wait doubles with every further
    failure, up to fifteen minutes. Overall: more than thirty failures in
    five minutes pause all logins for a minute, so that guessing from many
    addresses does not multiply the allowance.

    Kept in memory on purpose. A restart resets it, which costs an attacker
    a restart they cannot trigger, and it keeps the database free of
    addresses.
    """

    FREE = 5
    BASE = 2.0
    CAP = 15 * 60.0
    FORGET = 60 * 60.0
    GLOBAL_WINDOW = 5 * 60.0
    GLOBAL_LIMIT = 30
    GLOBAL_PAUSE = 60.0

    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self._lock = threading.Lock()
        self._buckets: dict[str, _Bucket] = {}
        self._recent: list[float] = []
        self._paused_until = 0.0

    def retry_after(self, client: str) -> int:
        """Seconds until this client may try again, 0 if now."""
        with self._lock:
            t = self.clock()
            wait = max(self._paused_until - t, 0.0)
            bucket = self._buckets.get(client)
            if bucket:
                wait = max(wait, bucket.blocked_until - t)
            return int(wait) + 1 if wait > 0 else 0

    def failed(self, client: str) -> None:
        with self._lock:
            t = self.clock()
            self._buckets = {k: b for k, b in self._buckets.items() if t - b.last < self.FORGET}
            bucket = self._buckets.setdefault(client, _Bucket())
            bucket.failures += 1
            bucket.last = t
            over = bucket.failures - self.FREE
            if over >= 0:
                bucket.blocked_until = t + min(self.BASE * (2**over), self.CAP)
            self._recent = [x for x in self._recent if t - x < self.GLOBAL_WINDOW] + [t]
            if len(self._recent) > self.GLOBAL_LIMIT:
                self._paused_until = t + self.GLOBAL_PAUSE

    def succeeded(self, client: str) -> None:
        with self._lock:
            self._buckets.pop(client, None)


class Auth:
    def __init__(self, db: DB, setup_code: str = "", throttle: Throttle | None = None) -> None:
        self.db = db
        self.throttle = throttle or Throttle()
        self._setup_code = ""
        if not self.configured:
            self._setup_code = normalise_code(setup_code) or normalise_code(new_setup_code())

    # -- password --------------------------------------------------------------

    @property
    def configured(self) -> bool:
        return bool(self.db.private("password"))

    @property
    def setup_code(self) -> str:
        """The code to print at start, grouped for reading. Empty once a
        password exists."""
        code = self._setup_code
        return "-".join(code[i : i + 4] for i in range(0, len(code), 4)) if code else ""

    def setup(self, code: str, password: str) -> None:
        """Set the first password. Raises ``PermissionError`` for a wrong
        code and ``PasswordRejected`` for a password that breaks the rules."""
        if self.configured or not self._setup_code:
            raise PermissionError("already set up")
        if not hmac.compare_digest(normalise_code(code).encode(), self._setup_code.encode()):
            raise PermissionError("wrong setup code")
        check_password_rules(password)
        self.db.set_private("password", _hasher.hash(password))
        self._setup_code = ""

    def verify(self, password: str) -> bool:
        stored = self.db.private("password")
        if not stored or len(password) > MAX_PASSWORD:
            return False
        try:
            _hasher.verify(stored, password)
        except (VerificationError, InvalidHashError):
            return False
        if _hasher.check_needs_rehash(stored):
            self.db.set_private("password", _hasher.hash(password))
        return True

    def change_password(self, current: str, new: str, keep: str = "") -> bool:
        """Changing the password ends every other session: whoever had access
        through the old one should not keep it. ``keep`` is the token of the
        session that made the change."""
        if not self.verify(current):
            return False
        check_password_rules(new)
        self.db.set_private("password", _hasher.hash(new))
        kept = self.db.session(hash_token(keep)) if keep else None
        self.db.delete_sessions(BROWSER)
        if kept:
            self.db.add_session(kept["token_hash"], BROWSER, kept["label"])
        return True

    def reset(self) -> str:
        """Forget the password and every session; returns a new setup code.
        Only reachable from the command line, i.e. by whoever runs the
        server."""
        self.db.set_private("password", "")
        self.db.delete_sessions()
        self._setup_code = normalise_code(new_setup_code())
        return self.setup_code

    # -- sessions --------------------------------------------------------------

    def login(self, password: str, client: str, label: str = "") -> str | None:
        """Returns a session token, or None. Check ``throttle.retry_after``
        first; this method counts the attempt."""
        if not self.verify(password):
            self.throttle.failed(client)
            return None
        self.throttle.succeeded(client)
        return self._issue(BROWSER, label)

    def _issue(self, kind: str, label: str = "") -> str:
        token = secrets.token_urlsafe(32)
        self.db.add_session(hash_token(token), kind, label)
        return token

    def check(self, token: str, kind: str = BROWSER) -> bool:
        if not token or len(token) > 200:
            return False
        digest = hash_token(token)
        session = self.db.session(digest)
        if not session or session["kind"] != kind:
            return False
        now = datetime.now().astimezone()
        created = datetime.fromisoformat(session["created"])
        last_seen = datetime.fromisoformat(session["last_seen"])
        if kind == BROWSER and (now - last_seen > SESSION_IDLE or now - created > SESSION_MAX):
            self.db.delete_session(digest)
            return False
        if now - last_seen > TOUCH_EVERY:
            self.db.touch_session(digest)
        return True

    def logout(self, token: str) -> None:
        if token:
            self.db.delete_session(hash_token(token))

    def logout_everywhere(self) -> None:
        self.db.delete_sessions(BROWSER)

    # -- fill helper -----------------------------------------------------------

    def new_helper_token(self, label: str = "") -> str:
        """One token per installed copy of the userscript, so a phone and a
        computer do not cut each other off. They do not expire, because they
        sit in an installed script; ``revoke_helper`` ends them all."""
        return self._issue(HELPER, label)

    def helper_count(self) -> int:
        return len(self.db.sessions(HELPER))

    def revoke_helper(self) -> None:
        self.db.delete_sessions(HELPER)

    def check_helper(self, token: str) -> bool:
        return self.check(token, HELPER)
