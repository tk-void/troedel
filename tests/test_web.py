"""The web layer end to end: what is reachable without a login, what a
logged-in browser can do, and what the fill helper's token is confined to."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from troedel import markets
from troedel.config import Settings
from troedel.providers import ProviderUnavailable
from troedel.web import security
from troedel.web.app import create_app, start_message
from troedel.worker import Worker

from .conftest import DRAFT, FakeEditor, FakeProvider, photo_bytes

PASSWORD = "correct horse battery"
CODE = "ABCD-EFGH-JKLM"
ORIGIN = {"Origin": "http://testserver"}


class Site:
    def __init__(self, tmp_path: Path, **overrides) -> None:
        self.settings = Settings(data_dir=tmp_path / "data", cutout=True, setup_code=CODE, **overrides)
        self.provider = FakeProvider()
        self.app = create_app(self.settings, start=False)
        self.ctx = self.app.state.ctx
        self.worker = Worker(
            self.ctx.db, self.settings, markets.get("de"), lambda: self.provider, FakeEditor(self.settings.model_dir)
        )
        self.ctx.worker = self.worker
        self.db = self.ctx.db

    def browser(self) -> TestClient:
        """A browser: sends Origin with what it posts, keeps cookies."""
        return TestClient(self.app, headers=ORIGIN, follow_redirects=False)

    def stranger(self) -> TestClient:
        return TestClient(self.app, follow_redirects=False)


@pytest.fixture
def site(tmp_path: Path) -> Site:
    return Site(tmp_path)


@pytest.fixture
def user(site: Site) -> TestClient:
    client = site.browser()
    response = client.post("/setup", data={"code": CODE, "password": PASSWORD, "repeat": PASSWORD})
    assert response.status_code == 303, response.text
    return client


def upload(client: TestClient, count: int = 1, **form: str) -> int:
    files = [("photos", (f"p{i}.jpg", photo_bytes(), "image/jpeg")) for i in range(count)]
    response = client.post("/api/items", files=files, data={"keywords": "Kinderschuhe Gr. 27", **form})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def page_paths(site: Site) -> list[tuple[str, str]]:
    """Every route with its methods, path parameters filled in."""
    out = []
    for route in site.app.routes:
        if isinstance(route, APIRoute):
            path = re.sub(r"\{[^}]+\}", "1", route.path)
            out += [(method, path) for method in route.methods if method != "HEAD"]
    return out


class TestNothingWithoutLogin:
    def test_every_route_is_closed_except_the_public_ones(self, site: Site, user: TestClient) -> None:
        """The check that matters most. A new route is covered automatically;
        if someone makes one public, this test names it."""
        open_routes = set()
        stranger = site.stranger()
        for method, path in page_paths(site):
            response = stranger.request(method, path, headers=ORIGIN)
            if response.status_code not in (401, 303):
                open_routes.add(path)
            elif response.status_code == 303:
                assert response.headers["location"] in ("/login", "/setup"), (method, path)
        # /setup is public too, but once a password exists it only redirects.
        assert open_routes == {"/login", "/health", "/manifest.webmanifest", "/troedel.user.js"}

    def test_public_routes_reveal_nothing(self, site: Site, user: TestClient) -> None:
        upload(user)
        stranger = site.stranger()
        assert stranger.get("/health").json() == {"status": "ok"}
        assert stranger.get("/troedel.user.js").status_code == 404
        assert "Kinderschuhe" not in stranger.get("/login").text

    def test_photos_need_a_login(self, site: Site, user: TestClient) -> None:
        item = site.db.item(upload(user))
        name = item["photos"][0]["file"] + ".jpg"
        assert user.get(f"/photo/{name}").status_code == 200
        assert site.stranger().get(f"/photo/{name}").status_code == 401

    def test_pages_redirect_to_the_login(self, site: Site, user: TestClient) -> None:
        response = site.stranger().get("/", headers={"Accept": "text/html"})
        assert response.status_code == 303 and response.headers["location"] == "/login"

    def test_before_setup_everything_leads_to_setup(self, site: Site) -> None:
        response = site.stranger().get("/", headers={"Accept": "text/html"})
        assert response.headers["location"] == "/setup"
        assert site.stranger().get("/api/status").status_code == 401

    def test_no_api_documentation_is_served(self, site: Site, user: TestClient) -> None:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert user.get(path).status_code == 404


class TestSetupAndLogin:
    def test_setup_needs_the_code(self, site: Site) -> None:
        client = site.browser()
        response = client.post("/setup", data={"code": "WRONG", "password": PASSWORD, "repeat": PASSWORD})
        assert response.status_code == 200 and "Code stimmt nicht" in response.text
        assert not site.ctx.auth.configured

    def test_setup_checks_the_repetition_and_the_rules(self, site: Site) -> None:
        client = site.browser()
        assert (
            "stimmen nicht überein"
            in client.post("/setup", data={"code": CODE, "password": PASSWORD, "repeat": "something else"}).text
        )
        assert "mindestens" in client.post("/setup", data={"code": CODE, "password": "short", "repeat": "short"}).text
        assert not site.ctx.auth.configured

    def test_setup_only_once(self, site: Site, user: TestClient) -> None:
        response = site.browser().post(
            "/setup", data={"code": CODE, "password": "another one 123", "repeat": "another one 123"}
        )
        assert response.status_code == 303 and response.headers["location"] == "/login"
        assert site.ctx.auth.verify(PASSWORD)

    def test_cookie_flags(self, site: Site) -> None:
        response = site.browser().post("/setup", data={"code": CODE, "password": PASSWORD, "repeat": PASSWORD})
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
        assert "secure" not in cookie, "plain HTTP: a Secure cookie would never come back"

    def test_cookie_is_secure_behind_an_https_proxy(self, tmp_path: Path) -> None:
        site = Site(tmp_path, trust_proxy=True)
        client = TestClient(
            site.app,
            follow_redirects=False,
            headers={
                "Origin": "https://troedel.example.org",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "troedel.example.org",
            },
        )
        response = client.post("/setup", data={"code": CODE, "password": PASSWORD, "repeat": PASSWORD})
        assert "secure" in response.headers["set-cookie"].lower()
        assert "strict-transport-security" in response.headers

    def test_forwarded_headers_are_ignored_without_trust(self, site: Site) -> None:
        client = TestClient(
            site.app,
            follow_redirects=False,
            headers={**ORIGIN, "X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.9"},
        )
        response = client.post("/setup", data={"code": CODE, "password": PASSWORD, "repeat": PASSWORD})
        assert "secure" not in response.headers["set-cookie"].lower()

    def test_login_logout(self, site: Site, user: TestClient) -> None:
        other = site.browser()
        assert other.post("/login", data={"password": "wrong password!"}).status_code == 401
        assert other.post("/login", data={"password": PASSWORD}).status_code == 303
        assert other.get("/api/status").status_code == 200
        other.post("/logout")
        assert other.get("/api/status").status_code == 401

    def test_guessing_is_throttled(self, site: Site, user: TestClient) -> None:
        other = site.browser()
        for _ in range(5):
            other.post("/login", data={"password": "wrong password!"})
        response = other.post("/login", data={"password": PASSWORD})
        assert response.status_code == 429 and int(response.headers["retry-after"]) > 0

    def test_throttle_cannot_be_dodged_with_a_forged_address(self, site: Site, user: TestClient) -> None:
        other = site.browser()
        for i in range(5):
            other.post("/login", data={"password": "wrong password!"}, headers={"X-Forwarded-For": f"198.51.100.{i}"})
        assert (
            other.post("/login", data={"password": PASSWORD}, headers={"X-Forwarded-For": "198.51.100.99"}).status_code
            == 429
        )

    def test_changing_the_password_signs_out_other_devices(self, site: Site, user: TestClient) -> None:
        other = site.browser()
        other.post("/login", data={"password": PASSWORD})
        response = user.post(
            "/settings/password", data={"current": PASSWORD, "new": "a new password 1", "repeat": "a new password 1"}
        )
        assert "saved=1" in response.headers["location"]
        assert user.get("/api/status").status_code == 200 and other.get("/api/status").status_code == 401

    def test_wrong_current_password(self, site: Site, user: TestClient) -> None:
        response = user.post(
            "/settings/password",
            data={"current": "nope nope nope", "new": "a new password 1", "repeat": "a new password 1"},
        )
        assert "error=wrong" in response.headers["location"] and site.ctx.auth.verify(PASSWORD)

    def test_sign_out_everywhere(self, site: Site, user: TestClient) -> None:
        user.post("/settings/sign-out-everywhere")
        assert user.get("/api/status").status_code == 401

    def test_login_page_warns_on_an_unencrypted_network_connection(self, site: Site, user: TestClient) -> None:
        assert "nicht verschlüsselt" in site.stranger().get("/login").text
        local = TestClient(site.app, base_url="http://localhost:8099")
        assert "nicht verschlüsselt" not in local.get("/login").text


class TestCrossSite:
    def test_a_foreign_site_cannot_act_with_the_cookie(self, site: Site, user: TestClient) -> None:
        item_id = upload(user)
        for headers in (
            {"Origin": "https://evil.example.org"},
            {"Origin": "null"},
            {"Origin": "http://testserver", "Sec-Fetch-Site": "cross-site"},
        ):
            response = user.delete(f"/api/items/{item_id}", headers=headers)
            assert response.status_code == 403, headers
        assert site.db.item(item_id) is not None

    def test_a_request_without_origin_is_refused(self, site: Site, user: TestClient) -> None:
        item_id = upload(user)
        bare = TestClient(site.app, cookies=dict(user.cookies), follow_redirects=False)
        assert bare.delete(f"/api/items/{item_id}").status_code == 403
        assert bare.get(f"/api/items/{item_id}").status_code == 200, "reading needs no origin"

    def test_referer_counts_when_origin_is_missing(self, site: Site, user: TestClient) -> None:
        item_id = upload(user)
        bare = TestClient(site.app, cookies=dict(user.cookies), follow_redirects=False)
        assert bare.delete(f"/api/items/{item_id}", headers={"Referer": "http://testserver/items/1"}).status_code == 200

    def test_login_cannot_be_posted_from_elsewhere(self, site: Site, user: TestClient) -> None:
        response = site.stranger().post(
            "/login", data={"password": PASSWORD}, headers={"Origin": "https://evil.example.org"}
        )
        assert response.status_code == 403

    def test_headers_on_every_response(self, site: Site, user: TestClient) -> None:
        for client, path in ((user, "/"), (site.stranger(), "/login"), (site.stranger(), "/api/status")):
            headers = client.get(path).headers
            csp = headers["content-security-policy"]
            assert "frame-ancestors 'none'" in csp and "default-src 'self'" in csp and "object-src 'none'" in csp
            assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]
            assert headers["x-content-type-options"] == "nosniff" and headers["x-frame-options"] == "DENY"
            assert headers["cache-control"] == "no-store"

    def test_inline_scripts_carry_the_nonce_of_their_response(self, site: Site, user: TestClient) -> None:
        response = user.get("/")
        nonce = re.search(r"'nonce-([^']+)'", response.headers["content-security-policy"]).group(1)
        assert f'<script nonce="{nonce}">' in response.text
        assert nonce not in user.get("/").headers["content-security-policy"], "a fresh nonce per response"
        assert not re.search(r"<script(?![^>]*(nonce=|src=))", response.text), "no inline script without nonce"
        assert not re.search(r"\son[a-z]+=", response.text), "no inline event handlers"


class TestItems:
    def test_from_upload_to_draft(self, site: Site, user: TestClient) -> None:
        item_id = upload(user, count=2, product="Superfit")
        assert user.get(f"/api/items/{item_id}").json()["in_progress"]
        site.worker.drain()
        state = user.get(f"/api/items/{item_id}").json()
        assert state["status"] == "draft" and state["title"] == DRAFT["title"] and not state["in_progress"]
        page = user.get(f"/items/{item_id}").text
        assert DRAFT["title"] in page and 'value="very_good" selected' in page
        assert "Kleinanzeigen" in page and "Vinted" in page
        assert user.get("/").status_code == 200 and user.get("/stats").status_code == 200

    def test_editing_fields(self, site: Site, user: TestClient) -> None:
        item_id = upload(user)
        site.worker.drain()
        response = user.patch(
            f"/api/items/{item_id}",
            json={
                "data": {"title": "  Neuer Titel ", "price": "25 €", "facts": "• eins\n- zwei\n\n", "condition": "good"}
            },
        )
        assert response.status_code == 200
        data = site.db.item(item_id)["data"]
        assert data["title"] == "Neuer Titel" and data["price"] == 25 and data["facts"] == ["eins", "zwei"]
        assert data["condition"] == "good"

    @pytest.mark.parametrize(
        "data", [{"nonsense": 1}, {"price": "viel"}, {"condition": "mint"}, {"shipping": "x"}, {"_model": "x"}]
    )
    def test_bad_edits_are_refused(self, site: Site, user: TestClient, data: dict) -> None:
        item_id = upload(user)
        site.worker.drain()
        assert user.patch(f"/api/items/{item_id}", json={"data": data}).status_code == 400

    def test_revise_undo(self, site: Site, user: TestClient) -> None:
        item_id = upload(user)
        site.worker.drain()
        site.provider.answers.append({**DRAFT, "price": 45})
        assert (
            user.post(f"/api/items/{item_id}/revise", json={"instruction": "Preis 45"}).json()["status"] == "revising"
        )
        assert user.patch(f"/api/items/{item_id}", json={"status": "archived"}).status_code == 409
        site.worker.drain()
        assert "data-changed" in user.get(f"/items/{item_id}").text
        assert user.post(f"/api/items/{item_id}/undo").status_code == 200
        assert site.db.item(item_id)["data"]["price"] == 15
        assert user.post(f"/api/items/{item_id}/undo").status_code == 409

    def test_failure_shows_what_to_do(self, site: Site, user: TestClient) -> None:
        site.provider.answers.append(ProviderUnavailable("limit"))
        item_id = upload(user)
        site.worker.drain()
        page = user.get(f"/items/{item_id}").text
        assert "ausgeschöpft" in page and "Erneut versuchen" in page
        assert "Technische Meldung" in page and "limit" in page, "the provider's own words are one tap away"
        assert user.post(f"/api/items/{item_id}/rewrite", json={"note": "Gr. 28"}).json()["status"] == "queued"
        site.worker.drain()
        assert site.db.item(item_id)["status"] == "draft" and "Gr. 28" in site.provider.calls[-1]["prompt"]

    def test_sold_and_stats(self, site: Site, user: TestClient) -> None:
        item_id = upload(user)
        site.worker.drain()
        assert user.put(f"/api/items/{item_id}/listed/vinted", json={"url": ""}).json()["status"] == "online"
        assert user.put(f"/api/items/{item_id}/listed/vinted", json={"url": "javascript:alert(1)"}).status_code == 400
        assert user.put(f"/api/items/{item_id}/listed/teapot", json={"url": ""}).status_code == 400
        assert (
            user.post(f"/api/items/{item_id}/sold", json={"price": "12,50", "via": "vinted"}).json()["status"] == "sold"
        )
        assert site.db.item(item_id)["sold_price"] == 12
        assert user.post(f"/api/items/{item_id}/sold", json={"price": "-3", "via": ""}).status_code == 400
        assert user.post(f"/api/items/{item_id}/sold", json={"price": "", "via": "teapot"}).status_code == 400
        assert "12 €" in user.get("/stats").text

    def test_delete_removes_the_files(self, site: Site, user: TestClient) -> None:
        item_id = upload(user)
        site.worker.drain()
        assert any(site.settings.photo_dir.iterdir())
        assert user.delete(f"/api/items/{item_id}").status_code == 200
        assert not any(site.settings.photo_dir.iterdir())
        assert user.get(f"/items/{item_id}").status_code == 404


class TestPhotos:
    def test_what_is_not_a_photo_is_refused_and_leaves_nothing(self, site: Site, user: TestClient) -> None:
        files = [
            ("photos", ("ok.jpg", photo_bytes(), "image/jpeg")),
            ("photos", ("evil.jpg", b"<script>alert(1)</script>", "image/jpeg")),
        ]
        assert user.post("/api/items", files=files, data={"keywords": "x"}).status_code == 400
        assert site.db.items() == []
        assert not site.settings.photo_dir.exists() or not any(site.settings.photo_dir.iterdir())

    def test_too_many(self, site: Site, user: TestClient) -> None:
        files = [("photos", (f"{i}.jpg", photo_bytes((40, 30)), "image/jpeg")) for i in range(13)]
        assert user.post("/api/items", files=files, data={"keywords": "x"}).status_code == 413

    def test_oversized_request_is_refused_before_it_is_read(self, site: Site, user: TestClient) -> None:
        response = user.post(
            "/api/items",
            content=b"x",
            headers={"Content-Length": str(10**10), "Content-Type": "multipart/form-data; boundary=x"},
        )
        assert response.status_code == 413

    @pytest.mark.parametrize(
        "name",
        [
            "../troedel.db",
            "..%2Ftroedel.db",
            "0123456789abcdef.png",
            "x.jpg",
            "0123456789abcdef-mask.png",
            "0123456789ABCDEF.jpg",
        ],
    )
    def test_photo_route_serves_only_photo_names(self, site: Site, user: TestClient, name: str) -> None:
        assert user.get(f"/photo/{name}").status_code == 404

    def test_looks_and_original(self, site: Site, user: TestClient) -> None:
        item_id = upload(user)
        site.worker.drain()
        photo = site.db.item(item_id)["photos"][0]
        assert user.get(f"/photo/{photo['file']}-studio.jpg").status_code == 200
        assert user.patch(f"/api/photos/{photo['id']}", json={"shown": "white"}).status_code == 400
        assert (
            user.patch(f"/api/photos/{photo['id']}", json={"shown": "original"}).json()["photos"][0]["shown"]
            == "original"
        )
        assert user.post(f"/api/items/{item_id}/look", json={"look": "sepia"}).status_code == 400
        assert user.post(f"/api/items/{item_id}/look", json={"look": "white"}).status_code == 200
        site.worker.drain()
        assert site.db.item(item_id)["photos"][0]["shown"] == "white"

    def test_the_last_photo_stays(self, site: Site, user: TestClient) -> None:
        item_id = upload(user, count=2)
        first, second = site.db.item(item_id)["photos"]
        assert user.delete(f"/api/photos/{first['id']}").status_code == 200
        assert user.delete(f"/api/photos/{second['id']}").status_code == 409

    def test_zip(self, site: Site, user: TestClient) -> None:
        item_id = upload(user, count=2)
        site.worker.drain()
        archive = zipfile.ZipFile(io.BytesIO(user.get(f"/items/{item_id}/photos.zip").content))
        assert archive.namelist() == [f"{item_id}-1.jpg", f"{item_id}-2.jpg"]

    def test_without_the_cutout_extra_photos_stay_original(self, tmp_path: Path) -> None:
        site = Site(tmp_path)
        object.__setattr__(site.settings, "cutout", False)
        client = site.browser()
        client.post("/setup", data={"code": CODE, "password": PASSWORD, "repeat": PASSWORD})
        item_id = upload(client)
        assert site.db.item(item_id)["photos"][0]["look"] == "original"
        assert client.post(f"/api/items/{item_id}/look", json={"look": "studio"}).status_code == 409


class TestSettings:
    def test_api_key_is_stored_apart_and_never_shown(self, site: Site, user: TestClient) -> None:
        key = "sk-test-" + "k" * 30
        response = user.post(
            "/settings/provider", data={"provider": "gemini", "model": "", "base_url": "", "api_key": key}
        )
        assert response.status_code == 303
        stored = site.settings.secrets_path
        assert json.loads(stored.read_text())["api_key"] == key and stored.stat().st_mode & 0o777 == 0o600
        assert key not in user.get("/settings").text and key[-4:] in user.get("/settings").text
        assert key not in site.settings.db_path.read_bytes().decode("latin-1")
        assert key.encode() not in user.get("/export.zip").content

    def test_changing_the_provider_drops_the_old_key(self, site: Site, user: TestClient) -> None:
        user.post("/settings/provider", data={"provider": "gemini", "api_key": "first-key-1234567"})
        user.post("/settings/provider", data={"provider": "gemini", "model": "other", "api_key": ""})
        assert site.ctx.secrets.get("api_key") == "first-key-1234567", "same provider: an empty field keeps the key"
        user.post("/settings/provider", data={"provider": "openai", "model": "m", "api_key": ""})
        assert site.ctx.secrets.get("api_key") == "", "a key is never sent to a provider it was not issued by"

    def test_environment_wins_over_the_stored_choice(self, tmp_path: Path) -> None:
        site = Site(tmp_path, provider="anthropic", api_key="from-environment")
        site.db.save_settings({"provider": "gemini"})
        assert site.ctx.provider_config()["provider"] == "anthropic"
        assert site.ctx.provider_config()["api_key"] == "from-environment"

    def test_settings_say_why_the_provider_cannot_be_used(self, site: Site, user: TestClient, monkeypatch) -> None:
        """A greyed-out test button without a reason is a dead end."""
        user.post("/settings/provider", data={"provider": "gemini"})
        assert "Es fehlt noch der API-Schlüssel" in user.get("/settings").text
        monkeypatch.setattr("shutil.which", lambda name: None)
        user.post("/settings/provider", data={"provider": "claude-cli"})
        page = user.get("/settings").text
        assert "nicht installiert" in page and "Docker-Container" in page

    def test_the_container_limit_is_stated_before_anyone_chooses(self, site: Site, user: TestClient) -> None:
        page = user.get("/settings").text
        assert "nicht im Container" in page and "Docker-Container" in page

    def test_unknown_provider_and_bad_address(self, site: Site, user: TestClient) -> None:
        assert user.post("/settings/provider", data={"provider": "teapot"}).status_code == 400
        assert (
            user.post("/settings/provider", data={"provider": "custom", "base_url": "file:///etc"}).status_code == 400
        )

    def test_general_settings_cannot_touch_the_others(self, site: Site, user: TestClient) -> None:
        user.post(
            "/settings", data={"location": "Musterstadt", "provider": "custom", "fill_helper": "1", "_password": "x"}
        )
        s = site.db.settings()
        assert s["location"] == "Musterstadt" and s["provider"] == "" and s["fill_helper"] == "0"
        assert site.ctx.auth.verify(PASSWORD)

    def test_market_texts_are_filled_in_once(self, site: Site, user: TestClient) -> None:
        assert site.db.settings()["footer"].startswith("Privatverkauf")
        user.post("/settings", data={"footer": ""})
        again = create_app(site.settings, start=False)
        assert again.state.ctx.db.settings()["footer"] == "", "an emptied text stays empty"

    def test_export_holds_database_and_originals(self, site: Site, user: TestClient) -> None:
        upload(user)
        site.worker.drain()
        names = zipfile.ZipFile(io.BytesIO(user.get("/export.zip").content)).namelist()
        assert "troedel.db" in names and len([n for n in names if n.startswith("photos/")]) == 1
        assert not any("studio" in n or "secrets" in n for n in names)

    def test_pages_render(self, site: Site, user: TestClient) -> None:
        for path in ("/settings", "/settings?welcome=1", "/settings?error=wrong", "/new", "/fill-helper", "/stats"):
            assert user.get(path).status_code == 200, path


class TestFillHelper:
    def install(self, site: Site, user: TestClient) -> str:
        assert user.post("/settings/fill-helper", data={"enable": "1"}).headers["location"] == "/fill-helper"
        response = user.post("/fill-helper/install")
        assert response.status_code == 303
        # Back to the page, which links to the script and shows its address
        # to paste into a userscript manager that did not open by itself.
        page = user.get(response.headers["location"]).text
        link = re.search(r'href="(/troedel\.user\.js\?install=[^"]+)"', page).group(1)
        assert f"{link}</code>" in page
        script = site.stranger().get(link)
        assert script.status_code == 200
        return re.search(r"const TOKEN = '([^']+)'", script.text).group(1)

    def test_page_links_straight_to_the_extension_for_each_browser(self, site: Site, user: TestClient) -> None:
        user.post("/settings/fill-helper", data={"enable": "1"})
        page = user.get("/fill-helper").text
        for browser, host in (
            ("firefox", "addons.mozilla.org"),
            ("chrome", "chromewebstore.google.com"),
            ("edge", "microsoftedge.microsoft.com"),
            ("safari", "apps.apple.com"),
        ):
            assert f'data-browser="{browser}"' in page and host in page, browser
        assert page.count('rel="noopener noreferrer"') >= 4

    def test_a_made_up_install_code_offers_nothing(self, site: Site, user: TestClient) -> None:
        user.post("/settings/fill-helper", data={"enable": "1"})
        page = user.get("/fill-helper?install=guess").text
        assert "troedel.user.js" not in page
        assert 'action="/fill-helper/install"' in page

    def test_off_by_default(self, site: Site, user: TestClient) -> None:
        assert user.post("/fill-helper/install").status_code == 404
        assert user.get("/api/helper/items").status_code == 404

    def test_token_reaches_its_own_paths_only(self, site: Site, user: TestClient) -> None:
        item_id = upload(user)
        site.worker.drain()
        token = self.install(site, user)
        helper = TestClient(site.app, headers={"Authorization": f"Bearer {token}"}, follow_redirects=False)
        listing = helper.get(f"/api/helper/items/{item_id}?platform=kleinanzeigen").json()
        assert listing["title"] == DRAFT["title"] and listing["photos"][0].startswith("http://testserver/photo/")
        assert helper.get(listing["photos"][0].removeprefix("http://testserver")).status_code == 200
        assert helper.put(f"/api/helper/items/{item_id}/listed/kleinanzeigen", json={"url": ""}).status_code == 200
        for method, path in (
            ("GET", "/"),
            ("GET", "/settings"),
            ("GET", f"/api/items/{item_id}"),
            ("DELETE", f"/api/items/{item_id}"),
            ("GET", "/export.zip"),
            ("POST", "/settings/provider"),
            ("POST", "/fill-helper/install"),
        ):
            assert helper.request(method, path).status_code == 401, (method, path)

    def test_a_wrong_token_gets_nothing(self, site: Site, user: TestClient) -> None:
        self.install(site, user)
        wrong = TestClient(site.app, headers={"Authorization": "Bearer made-up"})
        assert wrong.get("/api/helper/items").status_code == 401

    def test_a_session_token_is_not_a_helper_token(self, site: Site, user: TestClient) -> None:
        self.install(site, user)
        session = user.cookies[security.COOKIE]
        assert (
            TestClient(site.app, headers={"Authorization": f"Bearer {session}"}).get("/api/helper/items").status_code
            == 401
        )

    def test_switching_off_cuts_every_copy_off(self, site: Site, user: TestClient) -> None:
        token = self.install(site, user)
        user.post("/settings/fill-helper", data={"enable": "0"})
        helper = TestClient(site.app, headers={"Authorization": f"Bearer {token}"})
        assert helper.get("/api/helper/items").status_code == 401
        user.post("/settings/fill-helper", data={"enable": "1"})
        assert helper.get("/api/helper/items").status_code == 401, "switching on again does not revive old tokens"

    def test_install_link_is_useless_without_its_code(self, site: Site, user: TestClient) -> None:
        self.install(site, user)
        assert site.stranger().get("/troedel.user.js?install=guess").status_code == 404


class TestStartMessage:
    def test_says_where_to_go_and_shows_the_code_once_needed(self, tmp_path: Path) -> None:
        local = start_message(Settings(data_dir=tmp_path, port=8123), "ABCD-EFGH-JKLM")
        assert "http://localhost:8123" in local and "ABCD-EFGH-JKLM" in local
        assert "another device" not in local, "loopback only: there is no other device"

    def test_network_address_is_mentioned_when_reachable(self, tmp_path: Path) -> None:
        text = start_message(Settings(data_dir=tmp_path, host="0.0.0.0"), "")
        assert "http://localhost:8099" in text and "another device" in text
        assert "setup code" not in text, "nothing to enter once a password exists"


class TestOpen:
    def test_browser_opens_once_the_server_answers(self, monkeypatch, capsys):
        import threading
        import urllib.request
        import webbrowser

        from troedel import cli

        answers = iter([OSError("not yet"), OSError("not yet"), None])
        opened = threading.Event()
        urls = []

        class Up:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def urlopen(url, timeout):
            if (answer := next(answers)) is not None:
                raise answer
            return Up()

        monkeypatch.setattr(urllib.request, "urlopen", urlopen)
        monkeypatch.setattr("time.sleep", lambda s: None)
        monkeypatch.setattr(cli, "lan_address", lambda: "192.0.2.7")
        monkeypatch.setattr(webbrowser, "open", lambda url: (urls.append(url), opened.set()))
        cli._open_when_up(8099, lan=True)
        assert opened.wait(5)
        assert urls == ["http://localhost:8099"]
        assert "http://192.0.2.7:8099" in capsys.readouterr().out

    def test_never_opens_if_the_server_does_not_come_up(self, monkeypatch):
        import threading
        import urllib.request
        import webbrowser

        from troedel import cli

        def down(url, timeout):
            raise OSError("down")

        urls = []
        monkeypatch.setattr(urllib.request, "urlopen", down)
        monkeypatch.setattr("time.sleep", lambda s: None)
        monkeypatch.setattr(webbrowser, "open", urls.append)
        cli._open_when_up(8099, tries=3)
        for thread in threading.enumerate():
            if thread.name == "open-browser":
                thread.join(5)
        assert urls == []
