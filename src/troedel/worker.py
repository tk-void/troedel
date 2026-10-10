"""Two background threads: one for texts, one for photos.

Texts (writing, revising) only wait for the provider and should be served at
once; someone is actively waiting for "revise with AI". Photos (cut-out,
retouching) use the CPU and run one after another. With a single thread, a
revision could queue behind a retouch for minutes. The state is in the
database, so after a restart the work continues from there.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from . import imaging, listing
from .config import Settings
from .db import DB
from .providers import Provider, ProviderError

log = logging.getLogger(__name__)

DETAIL_LENGTH = 200


class Worker:
    def __init__(
        self,
        db: DB,
        settings: Settings,
        market: ModuleType,
        provider: Callable[[], Provider],
        editor: imaging.Editor | None = None,
    ) -> None:
        self.db = db
        self.s = settings
        self.market = market
        self.provider = provider
        """Called for every job, so a provider changed in the settings is
        used without a restart. Raises ``ProviderNotConfigured``."""
        self.editor = editor or imaging.Editor(settings.cutout_model, settings.model_dir)
        self.texts: queue.Queue[int] = queue.Queue()
        self.photos: queue.Queue[int] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()

    @property
    def folder(self) -> Path:
        return self.s.photo_dir

    def write(self, item_id: int) -> None:
        self.texts.put(item_id)

    def edit(self, photo_id: int) -> None:
        self.photos.put(photo_id)

    def start(self) -> None:
        self.resume()
        for name, q, job in (("texts", self.texts, self._write), ("photos", self.photos, self._edit)):
            thread = threading.Thread(target=self._loop, args=(q, job), name=name, daemon=True)
            thread.start()
            self._threads.append(thread)

    def resume(self) -> None:
        """Open work from the database into the queues."""
        # Finished photos whose file is missing: produce them again. With
        # the stored mask that takes seconds.
        for photo in self.db.done_photos():
            if (
                photo["look"] in imaging.EDITED_LOOKS
                and not imaging.paths(self.folder, photo["file"])[photo["look"]].is_file()
            ):
                self.db.requeue_photo(photo["id"])
        items, photos = self.db.open_work()
        for item_id in items:
            self.write(item_id)
        for photo_id in photos:
            self.edit(photo_id)

    def stop(self) -> None:
        self._stop.set()
        self.texts.put(-1)
        self.photos.put(-1)

    def drain(self) -> None:
        """Do everything queued now, texts first. For tests."""
        while not (self.texts.empty() and self.photos.empty()):
            while not self.texts.empty():
                self._write(self.texts.get_nowait())
            if not self.photos.empty():
                self._edit(self.photos.get_nowait())

    def _loop(self, q: queue.Queue[int], job: Callable[[int], None]) -> None:
        while not self._stop.is_set():
            ident = q.get()
            if ident < 0:
                break
            try:
                job(ident)
            except Exception:  # noqa: BLE001 - the worker must never die
                log.exception("Job %s failed", ident)

    def _model(self, key: str) -> str:
        return self.s.model or self.db.settings().get(key, "") or self.db.settings().get("model", "")

    def _analysis_photos(self, photos: list[dict[str, Any]]) -> list[bytes]:
        return [imaging.for_analysis(self.folder, p["file"]) for p in photos[: self.s.analysis_photos]]

    def _write(self, item_id: int) -> None:
        item = self.db.item(item_id)
        if item and item["status"] == "revising":
            self._revise(item)
            return
        if not item or item["status"] not in ("queued", "writing"):
            return
        self.db.set_state(item_id, "writing")
        try:
            data = listing.compose(
                self.provider(),
                self.market,
                self._analysis_photos(item["photos"]),
                item["keywords"],
                item["product"],
                item["note"],
                item["data"] or None,
                model=self._model("model"),
            )
        except ProviderError as exc:
            log.warning("Item %s: %s", item_id, exc)
            self.db.set_state(item_id, "failed", exc.code, str(exc)[:DETAIL_LENGTH])
            return
        self.db.save_draft(item_id, data)
        log.info("Item %s written", item_id)

    def _revise(self, item: dict[str, Any]) -> None:
        try:
            new = listing.revise(
                self.provider(),
                self.market,
                self._analysis_photos(item["photos"]),
                item["data"],
                item["instruction"],
                model=self._model("model"),
            )
        except ProviderError as exc:
            log.warning("Item %s: revision failed: %s", item["id"], exc)
            self.db.revision_failed(item["id"], exc.code, str(exc)[:DETAIL_LENGTH])
            return
        self.db.save_revision(item["id"], new)
        log.info("Item %s revised", item["id"])

    def _distractors(self, photo: dict[str, Any]) -> list[dict[str, Any]]:
        """Boxes around the distractors in this photo. The first time, the
        model is asked about all photos of the item that have none yet in
        one call, which saves calls."""
        if photo["distractors"] is not None:
            return photo["distractors"]
        item = self.db.item(photo["item_id"])
        assert item is not None
        limit = self.s.analysis_photos
        open_ = [p for p in item["photos"] if p["distractors"] is None]
        if photo["id"] not in [p["id"] for p in open_[:limit]]:
            open_ = [photo]
        open_ = open_[:limit]
        subject = " ".join(filter(None, [item["data"].get("title"), item["keywords"], item["product"]]))
        boxes = listing.find_distractors(
            self.provider(),
            self.market,
            [imaging.for_analysis(self.folder, p["file"]) for p in open_],
            subject,
            model=self._model("model_distractors"),
        )
        for p, b in zip(open_, boxes, strict=True):
            self.db.set_distractors(p["id"], b)
        return next(b for p, b in zip(open_, boxes, strict=True) if p["id"] == photo["id"])

    def _edit(self, photo_id: int) -> None:
        photo = self.db.photo(photo_id)
        if not photo or photo["state"] != "pending" or photo["look"] == "original":
            return
        try:
            boxes = self._distractors(photo) if photo["look"] == "tidy" else None
            self.editor.produce(self.folder, photo["file"], photo["look"], boxes)
        except ProviderError as exc:
            log.warning("Photo %s: distractors not found: %s", photo_id, exc)
            self._finish(photo, "failed")
            return
        except imaging.ImageError as exc:
            log.info("Photo %s not edited: %s", photo_id, exc)
            self._finish(photo, "failed")
            return
        except Exception:  # noqa: BLE001
            log.exception("Photo %s: editing failed", photo_id)
            self._finish(photo, "failed")
            return
        self._finish(photo, "done")

    def _finish(self, photo: dict[str, Any], state: str) -> None:
        """Only finish if the same look is still wanted. If it was changed
        in the meantime, the new job is already queued, and "done" would
        mean showing a file that does not exist."""
        current = self.db.photo(photo["id"])
        if current and current["look"] == photo["look"] and current["state"] == "pending":
            self.db.set_photo_state(photo["id"], state)
