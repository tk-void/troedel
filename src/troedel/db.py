"""SQLite: items, their photos, where they are listed, settings, sessions.

The fields of a listing (title, text, price ...) are stored as JSON in
``item.data``. They come from the model and are edited by hand afterwards; a
column per field would need a migration for every new field, and nothing ever
searches by them.

The schema is versioned with ``PRAGMA user_version``. To change it, append a
script to ``MIGRATIONS`` and never edit an existing one: databases out there
have already run them.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

MIGRATIONS: list[str] = [
    # 1
    """
    CREATE TABLE item (
        id           INTEGER PRIMARY KEY,
        created      TEXT NOT NULL,
        updated      TEXT NOT NULL,
        status       TEXT NOT NULL,
        keywords     TEXT NOT NULL DEFAULT '',
        product      TEXT NOT NULL DEFAULT '',
        note         TEXT NOT NULL DEFAULT '',
        data         TEXT NOT NULL DEFAULT '{}',
        suggestion   TEXT NOT NULL DEFAULT '{}',
        error        TEXT NOT NULL DEFAULT '',
        error_detail TEXT NOT NULL DEFAULT '',
        instruction  TEXT NOT NULL DEFAULT '',
        previous     TEXT NOT NULL DEFAULT '',
        sold_price   INTEGER,
        sold_at      TEXT,
        sold_via     TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE photo (
        id          INTEGER PRIMARY KEY,
        item_id     INTEGER NOT NULL REFERENCES item(id) ON DELETE CASCADE,
        pos         INTEGER NOT NULL,
        file        TEXT NOT NULL,
        state       TEXT NOT NULL DEFAULT 'pending',
        shown       TEXT NOT NULL DEFAULT 'studio',
        look        TEXT NOT NULL DEFAULT 'studio',
        distractors TEXT
    );
    CREATE INDEX photo_item ON photo(item_id, pos);
    CREATE TABLE listing (
        item_id   INTEGER NOT NULL REFERENCES item(id) ON DELETE CASCADE,
        platform  TEXT NOT NULL,
        url       TEXT NOT NULL DEFAULT '',
        since     TEXT NOT NULL,
        PRIMARY KEY (item_id, platform)
    );
    CREATE TABLE setting (
        key    TEXT PRIMARY KEY,
        value  TEXT NOT NULL
    );
    CREATE TABLE session (
        token_hash TEXT PRIMARY KEY,
        kind       TEXT NOT NULL,
        created    TEXT NOT NULL,
        last_seen  TEXT NOT NULL,
        label      TEXT NOT NULL DEFAULT ''
    );
    """,
]

BUSY = ("queued", "writing", "revising")
"""Item states in which the worker still has the item."""
MANUAL = ("draft", "online", "sold", "archived")
"""Item states a person may set."""
ITEM_STATES = (*BUSY, "failed", *MANUAL)
PHOTO_STATES = ("pending", "done", "failed", "off")
LOOKS = ("studio", "white", "tidy", "original")

DEFAULT_SETTINGS: dict[str, str] = {
    "location": "",
    "pickup": "",
    "shipping": "",
    "footer": "",
    "negotiable": "1",
    "look": "studio",
    "provider": "",
    "model": "",
    "model_distractors": "",
    "base_url": "",
    "fill_helper": "0",
}
"""Everything a person can change in the app. The empty texts are filled
from the market on first start, see ``markets``."""

PRIVATE_PREFIX = "_"
"""Settings that the app keeps for itself (password hash, flags). They are
never handed to a template or an API response."""

_AFTER_WORK = "CASE WHEN EXISTS (SELECT 1 FROM listing l WHERE l.item_id=item.id) THEN 'online' ELSE 'draft' END"


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class DB:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.con = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA foreign_keys=ON")
        self.lock = threading.RLock()
        self._migrate()

    def _migrate(self) -> None:
        version = self.con.execute("PRAGMA user_version").fetchone()[0]
        if version > len(MIGRATIONS):
            raise RuntimeError(
                f"{self.path} was written by a newer version of Trödel "
                f"(schema {version}, this one knows {len(MIGRATIONS)}). Update the app."
            )
        for number in range(version + 1, len(MIGRATIONS) + 1):
            # One transaction per step: a failed migration leaves the
            # database at the previous version instead of half way.
            self.con.executescript(f"BEGIN;\n{MIGRATIONS[number - 1]}\nPRAGMA user_version={number};\nCOMMIT;")

    def close(self) -> None:
        self.con.close()

    def backup(self, target: Path) -> None:
        """A consistent copy while the app keeps running."""
        with self.lock:
            copy = sqlite3.connect(target)
            try:
                self.con.backup(copy)
            finally:
                copy.close()

    def _q(self, sql: str, *args: Any) -> list[sqlite3.Row]:
        with self.lock:
            return self.con.execute(sql, args).fetchall()

    def _x(self, sql: str, *args: Any) -> int:
        with self.lock:
            return self.con.execute(sql, args).lastrowid or 0

    # -- items ---------------------------------------------------------------

    def add_item(self, keywords: str, product: str) -> int:
        t = now()
        return self._x(
            "INSERT INTO item (created, updated, status, keywords, product) VALUES (?,?,?,?,?)",
            t,
            t,
            "queued",
            keywords.strip(),
            product.strip(),
        )

    def item(self, item_id: int) -> dict[str, Any] | None:
        rows = self._q("SELECT * FROM item WHERE id=?", item_id)
        return self._item(rows[0]) if rows else None

    def items(self, states: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        if states:
            marks = ",".join("?" * len(states))
            rows = self._q(
                f"SELECT * FROM item WHERE status IN ({marks}) ORDER BY created DESC, id DESC",  # noqa: S608
                *states,
            )
        else:
            rows = self._q("SELECT * FROM item ORDER BY created DESC, id DESC")
        return [self._item(r) for r in rows]

    def count_by_state(self) -> dict[str, int]:
        return {r["status"]: r["n"] for r in self._q("SELECT status, COUNT(*) AS n FROM item GROUP BY status")}

    def takings(self) -> dict[str, int]:
        r = self._q("SELECT COUNT(*) AS n, COALESCE(SUM(sold_price), 0) AS total FROM item WHERE status='sold'")[0]
        return {"count": r["n"], "total": r["total"]}

    def _item(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["data"] = json.loads(d["data"] or "{}")
        d["suggestion"] = json.loads(d["suggestion"] or "{}")
        d["previous"] = json.loads(d["previous"]) if d.get("previous") else None
        d["photos"] = self.photos(d["id"])
        d["listings"] = {
            r["platform"]: dict(r) for r in self._q("SELECT * FROM listing WHERE item_id=? ORDER BY since", d["id"])
        }
        return d

    def set_state(self, item_id: int, status: str, error: str = "", detail: str = "") -> None:
        self._x(
            "UPDATE item SET status=?, error=?, error_detail=?, updated=? WHERE id=?",
            status,
            error,
            detail,
            now(),
            item_id,
        )

    def mark_sold(self, item_id: int, price: int | None, via: str) -> None:
        """Adding the amount or the platform later keeps the day of the sale."""
        t = now()
        self._x(
            "UPDATE item SET status='sold', sold_price=?, sold_via=?, "
            "sold_at=CASE WHEN status='sold' AND sold_at IS NOT NULL THEN sold_at ELSE ? END, "
            "error='', error_detail='', updated=? WHERE id=?",
            price,
            via,
            t,
            t,
            item_id,
        )

    def set_note(self, item_id: int, note: str) -> None:
        self._x("UPDATE item SET note=?, updated=? WHERE id=?", note.strip(), now(), item_id)

    def save_draft(self, item_id: int, suggestion: dict[str, Any]) -> None:
        """The model's suggestion becomes the listing. The suggestion itself
        is kept next to it, so the suggested price stays visible after the
        price has been changed by hand."""
        text = json.dumps(suggestion, ensure_ascii=False)
        with self.lock:
            self.con.execute(
                f"UPDATE item SET data=?, suggestion=?, error='', error_detail='', updated=?, "  # noqa: S608
                f"status={_AFTER_WORK} WHERE id=?",
                (text, text, now(), item_id),
            )

    def request_revision(self, item_id: int, instruction: str) -> None:
        self._x(
            "UPDATE item SET instruction=?, status='revising', error='', error_detail='', updated=? WHERE id=?",
            instruction.strip(),
            now(),
            item_id,
        )

    def save_revision(self, item_id: int, data: dict[str, Any]) -> None:
        """The state before is kept for "undo" and to show what changed."""
        with self.lock:
            self.con.execute(
                f"UPDATE item SET previous=data, data=?, instruction='', error='', error_detail='', "  # noqa: S608
                f"updated=?, status={_AFTER_WORK} WHERE id=?",
                (json.dumps(data, ensure_ascii=False), now(), item_id),
            )

    def revision_failed(self, item_id: int, error: str, detail: str = "") -> None:
        """The text stays as it was; only the message is added."""
        self._x(
            f"UPDATE item SET error=?, error_detail=?, status={_AFTER_WORK} WHERE id=?",  # noqa: S608
            error,
            detail,
            item_id,
        )

    def undo_revision(self, item_id: int) -> bool:
        with self.lock:
            rows = self._q("SELECT previous FROM item WHERE id=?", item_id)
            if not rows or not rows[0]["previous"]:
                return False
            self.con.execute("UPDATE item SET data=previous, previous='', updated=? WHERE id=?", (now(), item_id))
            return True

    def keep_revision(self, item_id: int) -> None:
        self._x("UPDATE item SET previous='', error='', error_detail='' WHERE id=?", item_id)

    def update_data(self, item_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            rows = self._q("SELECT data FROM item WHERE id=?", item_id)
            if not rows:
                raise KeyError(item_id)
            data = json.loads(rows[0]["data"] or "{}")
            data.update(fields)
            self.con.execute(
                "UPDATE item SET data=?, updated=? WHERE id=?", (json.dumps(data, ensure_ascii=False), now(), item_id)
            )
            return data

    def delete_item(self, item_id: int) -> list[str]:
        """Deletes the item and returns the photo files that can go."""
        files = [p["file"] for p in self.photos(item_id)]
        self._x("DELETE FROM item WHERE id=?", item_id)
        return files

    # -- photos --------------------------------------------------------------

    def add_photo(self, item_id: int, file: str, look: str) -> int:
        """``look`` original means: leave the photo alone."""
        pos = self._q("SELECT COALESCE(MAX(pos), -1) + 1 AS p FROM photo WHERE item_id=?", item_id)[0]["p"]
        edit = look != "original"
        return self._x(
            "INSERT INTO photo (item_id, pos, file, state, shown, look) VALUES (?,?,?,?,?,?)",
            item_id,
            pos,
            file,
            "pending" if edit else "off",
            "original",
            look,
        )

    def order_look(self, photo_id: int, look: str) -> None:
        """Ask for a look. The worker produces it."""
        if look == "original":
            self._x("UPDATE photo SET look='original', shown='original', state='off' WHERE id=?", photo_id)
        else:
            self._x("UPDATE photo SET look=?, shown='original', state='pending' WHERE id=?", look, photo_id)

    def forget_distractors(self, photo_id: int) -> None:
        self._x("UPDATE photo SET distractors=NULL WHERE id=?", photo_id)

    def set_distractors(self, photo_id: int, boxes: list[dict[str, Any]]) -> None:
        self._x("UPDATE photo SET distractors=? WHERE id=?", json.dumps(boxes, ensure_ascii=False), photo_id)

    def photos(self, item_id: int) -> list[dict[str, Any]]:
        return [self._photo(r) for r in self._q("SELECT * FROM photo WHERE item_id=? ORDER BY pos, id", item_id)]

    def photo(self, photo_id: int) -> dict[str, Any] | None:
        rows = self._q("SELECT * FROM photo WHERE id=?", photo_id)
        return self._photo(rows[0]) if rows else None

    @staticmethod
    def _photo(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["distractors"] = json.loads(d["distractors"]) if d.get("distractors") else None
        return d

    def set_photo_state(self, photo_id: int, state: str) -> None:
        """Done means the look is shown; it can still be switched back to the
        original afterwards. Anything else shows the original."""
        with self.lock:
            self.con.execute("UPDATE photo SET state=? WHERE id=?", (state, photo_id))
            if state == "done":
                self.con.execute("UPDATE photo SET shown=look WHERE id=?", (photo_id,))
            else:
                self.con.execute("UPDATE photo SET shown='original' WHERE id=?", (photo_id,))

    def done_photos(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._q("SELECT * FROM photo WHERE state='done'")]

    def requeue_photo(self, photo_id: int) -> None:
        """Send a photo through the editing again without touching what is
        shown, for looks whose file has gone missing."""
        self._x("UPDATE photo SET state='pending' WHERE id=?", photo_id)

    def show(self, photo_id: int, shown: str) -> None:
        self._x("UPDATE photo SET shown=? WHERE id=?", shown, photo_id)

    def move_photo(self, photo_id: int, direction: int) -> None:
        with self.lock:
            photo = self.photo(photo_id)
            if not photo:
                return
            row = self.photos(photo["item_id"])
            i = next(i for i, x in enumerate(row) if x["id"] == photo_id)
            j = i + direction
            if not 0 <= j < len(row):
                return
            row[i], row[j] = row[j], row[i]
            for pos, x in enumerate(row):
                self.con.execute("UPDATE photo SET pos=? WHERE id=?", (pos, x["id"]))

    def delete_photo(self, photo_id: int) -> str | None:
        photo = self.photo(photo_id)
        if not photo:
            return None
        self._x("DELETE FROM photo WHERE id=?", photo_id)
        return photo["file"]

    def open_work(self) -> tuple[list[int], list[int]]:
        """What is left to do after a restart: items without a text, photos
        without their look."""
        items = [
            r["id"] for r in self._q("SELECT id FROM item WHERE status IN ('queued','writing','revising') ORDER BY id")
        ]
        photos = [r["id"] for r in self._q("SELECT id FROM photo WHERE state='pending' ORDER BY id")]
        return items, photos

    # -- listings ------------------------------------------------------------

    def set_listed(self, item_id: int, platform: str, url: str) -> None:
        with self.lock:
            self.con.execute(
                "INSERT INTO listing (item_id, platform, url, since) VALUES (?,?,?,?) "
                "ON CONFLICT(item_id, platform) DO UPDATE SET url=excluded.url",
                (item_id, platform, url.strip(), now()),
            )
            self.con.execute(
                "UPDATE item SET status='online', updated=? WHERE id=? AND status='draft'", (now(), item_id)
            )

    def set_unlisted(self, item_id: int, platform: str) -> None:
        with self.lock:
            self.con.execute("DELETE FROM listing WHERE item_id=? AND platform=?", (item_id, platform))
            left = self.con.execute("SELECT COUNT(*) FROM listing WHERE item_id=?", (item_id,)).fetchone()[0]
            if not left:
                self.con.execute(
                    "UPDATE item SET status='draft', updated=? WHERE id=? AND status='online'", (now(), item_id)
                )

    # -- settings ------------------------------------------------------------

    def settings(self) -> dict[str, str]:
        """The settings a person can change, with defaults filled in."""
        values = dict(DEFAULT_SETTINGS)
        values.update(
            {r["key"]: r["value"] for r in self._q("SELECT * FROM setting") if not r["key"].startswith(PRIVATE_PREFIX)}
        )
        return values

    def save_settings(self, values: dict[str, str]) -> None:
        with self.lock:
            for key, value in values.items():
                if key in DEFAULT_SETTINGS:
                    self._put(key, value.strip())

    def private(self, key: str) -> str:
        rows = self._q("SELECT value FROM setting WHERE key=?", PRIVATE_PREFIX + key)
        return rows[0]["value"] if rows else ""

    def set_private(self, key: str, value: str) -> None:
        self._put(PRIVATE_PREFIX + key, value)

    def _put(self, key: str, value: str) -> None:
        with self.lock:
            self.con.execute(
                "INSERT INTO setting VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    # -- sessions ------------------------------------------------------------

    def add_session(self, token_hash: str, kind: str, label: str = "") -> None:
        t = now()
        self._x(
            "INSERT INTO session (token_hash, kind, created, last_seen, label) VALUES (?,?,?,?,?)",
            token_hash,
            kind,
            t,
            t,
            label[:120],
        )

    def session(self, token_hash: str) -> dict[str, Any] | None:
        rows = self._q("SELECT * FROM session WHERE token_hash=?", token_hash)
        return dict(rows[0]) if rows else None

    def touch_session(self, token_hash: str) -> None:
        self._x("UPDATE session SET last_seen=? WHERE token_hash=?", now(), token_hash)

    def delete_session(self, token_hash: str) -> None:
        self._x("DELETE FROM session WHERE token_hash=?", token_hash)

    def delete_sessions(self, kind: str | None = None) -> None:
        if kind is None:
            self._x("DELETE FROM session")
        else:
            self._x("DELETE FROM session WHERE kind=?", kind)

    def sessions(self, kind: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self._q("SELECT * FROM session WHERE kind=? ORDER BY last_seen DESC", kind)]
