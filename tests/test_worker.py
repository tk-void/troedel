from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from troedel import imaging, listing, markets
from troedel.config import Settings
from troedel.db import DB, MIGRATIONS
from troedel.providers import ProviderError, ProviderNotConfigured, ProviderUnavailable
from troedel.worker import Worker

from .conftest import DRAFT, FakeProvider, photo_bytes

DE = markets.get("de")


def add_item(db: DB, settings: Settings, look: str = "studio", photos: int = 1) -> int:
    item_id = db.add_item("Kinderschuhe Gr. 27", "")
    for _ in range(photos):
        db.add_photo(item_id, imaging.store(imaging.read(photo_bytes()), settings.photo_dir), look)
    return item_id


class TestWriting:
    def test_draft_from_photos(self, db: DB, settings: Settings, worker: Worker, provider: FakeProvider) -> None:
        item_id = add_item(db, settings)
        worker.resume()
        worker.drain()
        item = db.item(item_id)
        assert item["status"] == "draft" and item["data"]["title"] == DRAFT["title"]
        assert item["data"]["_model"] == "fake-1" and item["suggestion"]["price"] == 15
        call = provider.calls[0]
        assert "Kinderschuhe Gr. 27" in call["prompt"] and len(call["images"]) == 1
        assert item["photos"][0]["state"] == "done" and item["photos"][0]["shown"] == "studio"

    def test_only_the_first_photos_are_sent(
        self, db: DB, settings: Settings, worker: Worker, provider: FakeProvider
    ) -> None:
        add_item(db, settings, look="original", photos=6)
        worker.resume()
        worker.drain()
        assert len(provider.calls[0]["images"]) == settings.analysis_photos

    @pytest.mark.parametrize(
        "error, code",
        [
            (ProviderUnavailable("limit"), "unavailable"),
            (ProviderNotConfigured("no key"), "not_configured"),
            (ProviderError("nope", "auth"), "auth"),
        ],
    )
    def test_failure_is_recorded_and_nothing_is_lost(
        self, db: DB, settings: Settings, worker: Worker, provider: FakeProvider, error: Exception, code: str
    ) -> None:
        item_id = add_item(db, settings, look="original")
        provider.answers.append(error)
        worker.resume()
        worker.drain()
        item = db.item(item_id)
        assert item["status"] == "failed" and item["error"] == code and item["photos"]
        db.set_state(item_id, "queued")
        worker.write(item_id)
        worker.drain()
        assert db.item(item_id)["status"] == "draft"

    def test_provider_is_looked_up_per_job(self, db: DB, settings: Settings) -> None:
        """Changing the provider in the settings needs no restart."""
        first, second = FakeProvider(), FakeProvider()
        current = [first]
        worker = Worker(db, settings, DE, lambda: current[0])
        a = add_item(db, settings, look="original")
        worker.write(a)
        worker.drain()
        current[0] = second
        b = add_item(db, settings, look="original")
        worker.write(b)
        worker.drain()
        assert len(first.calls) == 1 and len(second.calls) == 1


class TestRevising:
    def test_revision_keeps_the_previous_state_for_undo(
        self, db: DB, settings: Settings, worker: Worker, provider: FakeProvider
    ) -> None:
        item_id = add_item(db, settings, look="original")
        worker.resume()
        worker.drain()
        provider.answers.append({**DRAFT, "price": 45})
        db.request_revision(item_id, "Preis 45 €")
        worker.write(item_id)
        worker.drain()
        item = db.item(item_id)
        assert item["data"]["price"] == 45 and item["previous"]["price"] == 15 and item["status"] == "draft"
        assert "Preis 45 €" in provider.calls[-1]["prompt"]
        assert db.undo_revision(item_id) and db.item(item_id)["data"]["price"] == 15
        assert not db.undo_revision(item_id)

    def test_failed_revision_changes_nothing(
        self, db: DB, settings: Settings, worker: Worker, provider: FakeProvider
    ) -> None:
        item_id = add_item(db, settings, look="original")
        worker.resume()
        worker.drain()
        db.set_listed(item_id, "vinted", "")
        provider.answers.append(ProviderUnavailable("limit"))
        db.request_revision(item_id, "kürzer")
        worker.write(item_id)
        worker.drain()
        item = db.item(item_id)
        assert item["status"] == "online" and item["error"] == "unavailable"
        assert item["data"]["title"] == DRAFT["title"]


class TestPhotos:
    def test_tidy_asks_once_for_all_photos(
        self, db: DB, settings: Settings, worker: Worker, provider: FakeProvider
    ) -> None:
        item_id = add_item(db, settings, look="tidy", photos=3)
        boxes = {"photos": [{"photo": 2, "distractors": [{"what": "Poster", "x0": 0, "y0": 0, "x1": 200, "y1": 200}]}]}
        provider.answers += [dict(DRAFT), boxes]
        worker.resume()
        worker.drain()
        photos = db.item(item_id)["photos"]
        assert [p["state"] for p in photos] == ["done"] * 3
        assert [len(p["distractors"]) for p in photos] == [0, 1, 0]
        assert len(provider.calls) == 2, "one call for the text, one for all three photos"

    def test_a_look_changed_meanwhile_is_not_marked_done(self, db: DB, settings: Settings, worker: Worker) -> None:
        item_id = add_item(db, settings)
        photo = db.item(item_id)["photos"][0]
        db.order_look(photo["id"], "white")
        worker._finish(photo, "done")
        assert db.photo(photo["id"])["state"] == "pending"

    def test_failed_cut_out_falls_back_to_the_original(
        self, db: DB, settings: Settings, worker: Worker, monkeypatch
    ) -> None:
        def broken(*args, **kwargs):
            raise imaging.ImageError("no object found")

        monkeypatch.setattr(worker.editor, "produce", broken)
        item_id = add_item(db, settings)
        worker.resume()
        worker.drain()
        photo = db.item(item_id)["photos"][0]
        assert photo["state"] == "failed" and photo["shown"] == "original"

    def test_missing_files_are_produced_again_after_a_restart(self, db: DB, settings: Settings, worker: Worker) -> None:
        item_id = add_item(db, settings)
        worker.resume()
        worker.drain()
        photo = db.item(item_id)["photos"][0]
        imaging.discard_look(settings.photo_dir, photo["file"], "studio")
        worker.resume()
        worker.drain()
        assert imaging.paths(settings.photo_dir, photo["file"])["studio"].is_file()


class TestListing:
    def test_clean(self) -> None:
        d = listing.clean(
            {
                **DRAFT,
                "title": "  x  ",
                "facts": [" a ", "", "b"],
                "price_min": 30,
                "price_max": 10,
                "search_terms": [str(i) for i in range(12)],
            }
        )
        assert d["title"] == "x" and d["facts"] == ["a", "b"]
        assert (d["price_min"], d["price_max"]) == (10, 30) and len(d["search_terms"]) == 8

    @pytest.mark.parametrize(
        "box, kept",
        [
            ({"x0": 10, "y0": 10, "x1": 300, "y1": 300}, True),
            ({"x0": 300, "y0": 300, "x1": 10, "y1": 10}, True),
            ({"x0": 0, "y0": 0, "x1": 1000, "y1": 1000}, False),
            ({"x0": 10, "y0": 10, "x1": 12, "y1": 300}, False),
            ({"x0": "a", "y0": 0, "x1": 1, "y1": 1}, False),
        ],
    )
    def test_boxes_are_checked(self, box: dict, kept: bool) -> None:
        assert (listing._box({"what": "x", **box}) is not None) is kept

    def test_platforms_cut_the_listing_to_fit(self) -> None:
        long_title = "Kinderschuhe " + "sehr schön " * 10
        settings = {"location": "Musterstadt", "negotiable": "1", **DE.DEFAULT_TEXTS}
        ka, vinted, ebay, _fb = DE.platforms({**DRAFT, "title": long_title}, settings)
        assert len(ka.value("title")) <= 65 and len(vinted.value("title")) <= 60 and len(ebay.value("title")) <= 80
        assert ka.value("condition") == "Sehr gut" and ebay.value("condition") == "Gebraucht"
        assert "Abholung möglich in Musterstadt." in ka.value("description")
        assert "Privatverkauf" in ka.value("description") and "Privatverkauf" not in vinted.value("description")
        assert ka.value("price") == "15 €" and ka.fill_helper and not ebay.fill_helper

    def test_pickup_only_drops_the_shipping_line(self) -> None:
        settings = {"location": "", "negotiable": "0", **DE.DEFAULT_TEXTS}
        text = DE.platforms({**DRAFT, "shipping": "pickup"}, settings)[0].value("description")
        assert "Versand" not in text


class TestDatabase:
    def test_schema_version_is_recorded(self, db: DB) -> None:
        assert db.con.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)

    def test_reopening_does_not_migrate_again(self, db: DB, settings: Settings) -> None:
        db.add_item("x", "")
        db.close()
        assert len(DB(settings.db_path).items()) == 1

    def test_a_newer_database_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "future.db"
        con = sqlite3.connect(path)
        con.execute(f"PRAGMA user_version={len(MIGRATIONS) + 1}")
        con.close()
        with pytest.raises(RuntimeError, match="newer version"):
            DB(path)

    def test_backup_is_a_usable_copy(self, db: DB, tmp_path: Path) -> None:
        db.add_item("x", "")
        db.backup(tmp_path / "copy.db")
        assert len(DB(tmp_path / "copy.db").items()) == 1

    def test_listing_state_follows_the_platforms(self, db: DB) -> None:
        item_id = db.add_item("x", "")
        db.save_draft(item_id, dict(DRAFT))
        db.set_listed(item_id, "vinted", "")
        db.set_listed(item_id, "ebay", "")
        assert db.item(item_id)["status"] == "online"
        db.set_unlisted(item_id, "vinted")
        assert db.item(item_id)["status"] == "online"
        db.set_unlisted(item_id, "ebay")
        assert db.item(item_id)["status"] == "draft"

    def test_sale_day_survives_a_later_correction(self, db: DB) -> None:
        item_id = db.add_item("x", "")
        db.mark_sold(item_id, 10, "")
        db.con.execute("UPDATE item SET sold_at='2026-01-02T10:00:00+00:00'")
        db.mark_sold(item_id, 12, "vinted")
        item = db.item(item_id)
        assert item["sold_at"].startswith("2026-01-02") and item["sold_price"] == 12

    def test_unknown_settings_are_ignored(self, db: DB) -> None:
        db.save_settings({"location": " Musterstadt ", "_password": "x", "nonsense": "y"})
        s = db.settings()
        assert s["location"] == "Musterstadt" and "nonsense" not in s and db.private("password") == ""
