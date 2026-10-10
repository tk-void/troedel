"""Pages for people and the JSON API those pages call with ``fetch``.

``create_app`` builds everything from a ``Settings`` object, so tests and
the command line start the same app. Access control is not in this module:
see ``security``, which every request passes first.
"""

from __future__ import annotations

import io
import logging
import re
import secrets
import time
import zipfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .. import __version__, imaging, listing, markets, providers, stats
from ..auth import MIN_PASSWORD, Auth, PasswordRejected
from ..config import Settings
from ..db import BUSY, DB, LOOKS, MANUAL
from ..secrets_store import SecretsStore
from ..worker import Worker
from . import security, text

log = logging.getLogger("troedel")

HERE = Path(__file__).resolve().parent
PHOTO_VERSION = 1
"""Part of every photo address. Raise it to get past browser caches after a
change to how photos are produced."""
INSTALL_SECONDS = 600
PHOTO_NAME = re.compile(r"^[0-9a-f]{16}(-studio|-white|-tidy)?(-t)?\.jpg$")

EDITABLE: dict[str, type] = {
    "title": str,
    "description": str,
    "category": str,
    "brand": str,
    "model": str,
    "size": str,
    "color": str,
    "material": str,
    "condition": str,
    "shipping": str,
    "price": int,
    "facts": list,
    "defects": list,
    # Ticked "please check" entries: texts, not positions, so they do not
    # slide onto the wrong entry after a revision.
    "checked": list,
}


class Change(BaseModel):
    data: dict[str, Any] = {}
    status: str | None = None


class Sale(BaseModel):
    price: str = ""
    via: str = ""


class Note(BaseModel):
    note: str = ""


class Instruction(BaseModel):
    instruction: str


class LookChoice(BaseModel):
    look: str
    again: bool = False
    """Discard the existing files of this look (and for "tidy" have the
    distractors searched again), when a result is not good."""


class PhotoChange(BaseModel):
    shown: str | None = None
    move: int | None = None
    retry: bool = False


class Link(BaseModel):
    url: str = ""


@dataclass
class Context:
    settings: Settings
    db: DB
    auth: Auth
    worker: Worker
    market: ModuleType
    secrets: SecretsStore

    @property
    def cutout(self) -> bool:
        wanted = self.settings.cutout
        return imaging.available() if wanted is None else wanted

    def provider_config(self) -> dict[str, str]:
        """Where each provider setting comes from. The environment wins and
        locks the setting in the interface."""
        s, stored = self.settings, self.db.settings()
        return {
            "provider": s.provider or stored["provider"],
            "model": s.model or stored["model"],
            "base_url": s.base_url or stored["base_url"],
            "api_key": s.api_key or self.secrets.get("api_key"),
        }

    def provider(self) -> providers.Provider:
        c = self.provider_config()
        return providers.build(c["provider"], api_key=c["api_key"], model=c["model"], base_url=c["base_url"])

    def provider_ready(self) -> bool:
        return self.provider_missing() is None

    def provider_missing(self) -> str | None:
        """None if the provider can be used, otherwise what is missing."""
        try:
            self.provider()
        except providers.ProviderNotConfigured as exc:
            return exc.missing or "provider"
        except providers.ProviderError:
            return "provider"
        return None


def photo_url(photo: dict[str, Any], thumb: bool = False, shown: str | None = None) -> str:
    look = shown or photo["shown"]
    variant = f"-{look}" if look in imaging.EDITED_LOOKS and photo["state"] == "done" else ""
    return f"/photo/{photo['file']}{variant}{'-t' if thumb else ''}.jpg?v={PHOTO_VERSION}"


def cover(item: dict[str, Any]) -> str:
    return photo_url(item["photos"][0], thumb=True) if item["photos"] else ""


def in_progress(item: dict[str, Any]) -> bool:
    return item["status"] in BUSY or any(p["state"] == "pending" for p in item["photos"])


def changed_fields(item: dict[str, Any]) -> list[str]:
    """What the last revision changed, to highlight it."""
    if not item.get("previous"):
        return []
    return [k for k in text.FIELDS if item["previous"].get(k) != item["data"].get(k)]


def summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "status": item["status"],
        "error": item["error"],
        "title": item["data"].get("title", ""),
        "in_progress": in_progress(item),
        "photos": [
            {"id": p["id"], "state": p["state"], "shown": p["shown"], "look": p["look"], "file": p["file"]}
            for p in item["photos"]
        ],
        "updated": item["updated"],
    }


def start_message(settings: Settings, setup_code: str) -> str:
    """What to do next, for whoever just started the server. Printed, not
    logged at a level someone might filter: without the setup code nobody
    can set the first password."""
    local = settings.host in ("127.0.0.1", "localhost", "::1")
    lines = ["", f"  Trödel is running. Open:  http://localhost:{settings.port}"]
    if not local:
        # In a container the published port may differ from this one.
        lines.append(f"  From another device:      http://<this computer's address>:{settings.port}")
    if setup_code:
        lines += ["", "  First start: enter this setup code there and choose a password.", "", f"      {setup_code}"]
    return "\n".join(lines) + "\n"


def create_app(settings: Settings, *, worker: Worker | None = None, start: bool = True) -> FastAPI:
    db = DB(settings.db_path)
    market = markets.get()
    # First start: the texts a listing ends with, in the market's language.
    stored = db.settings()
    db.save_settings(
        {k: v for k, v in market.DEFAULT_TEXTS.items() if not stored.get(k) and not db.private("defaults_set")}
    )
    db.set_private("defaults_set", "1")

    ctx = Context(
        settings,
        db,
        Auth(db, settings.setup_code),
        worker,
        market,  # type: ignore[arg-type]
        SecretsStore(settings.secrets_path),
    )
    ctx.worker = worker or Worker(db, settings, market, ctx.provider)
    ctx.worker.db = db
    installs: dict[str, tuple[str, float]] = {}
    """Install code -> (helper token, valid until). In memory only."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log.info("Trödel %s, data in %s", __version__, settings.data_dir.resolve())
        print(start_message(settings, ctx.auth.setup_code), flush=True)  # noqa: T201
        if start:
            ctx.worker.start()
        yield
        ctx.worker.stop()

    app = FastAPI(
        title="Trödel", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.ctx = ctx
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    max_body = settings.max_photos * security.MAX_PHOTO_BYTES + (1 << 20)
    security.install(
        app, ctx.auth, settings.trust_proxy, max_body, helper_enabled=lambda: db.settings()["fill_helper"] == "1"
    )

    pages = Jinja2Templates(directory=str(HERE / "templates"))
    pages.env.filters["lookup"] = lambda key, table: table.get(key, key)
    pages.env.globals.update(
        photo_url=photo_url,
        cover=cover,
        date=text.date,
        model_name=text.model_name,
        pieces=text.pieces,
        version=__version__,
        STATUS=text.STATUS,
        LOOKS=text.LOOKS,
        LOOK_HINTS=text.LOOK_HINTS,
        FIELDS=text.FIELDS,
        ERRORS=text.ERRORS,
        MONTHS=text.MONTHS,
        MONTHS_SHORT=text.MONTHS_SHORT,
        CONDITIONS=market.CONDITIONS,
        SHIPPING=market.SHIPPING,
        CURRENCY=market.CURRENCY,
        PLATFORM_NAMES=market.NAMES,
        PLATFORM_SHORT=market.SHORT,
        PLATFORM_BADGES=market.BADGES,
        PLATFORM_COLORS=market.COLORS,
        SOLD_VIA={**market.NAMES, **market.SOLD_ELSEWHERE},
    )
    sold_via = {**market.NAMES, **market.SOLD_ELSEWHERE}

    def page(request: Request, name: str, **values: Any) -> HTMLResponse:
        return pages.TemplateResponse(request, name, {"nonce": request.state.nonce, **values})

    def fail(status: int, key: str, **values: Any) -> HTTPException:
        return HTTPException(status, text.API[key].format(**values))

    def item_or_404(item_id: int) -> dict[str, Any]:
        item = db.item(item_id)
        if not item:
            raise fail(404, "not_found")
        return item

    def not_busy(item: dict[str, Any]) -> None:
        if item["status"] in BUSY:
            raise fail(409, "busy")

    # -- signing in ------------------------------------------------------------

    @app.get("/setup", response_class=HTMLResponse)
    async def setup_page(request: Request) -> Response:
        if ctx.auth.configured:
            return RedirectResponse("/login", status_code=303)
        return page(request, "setup.html", error="", min_password=MIN_PASSWORD)

    @app.post("/setup")
    async def setup(
        request: Request, code: str = Form(""), password: str = Form(""), repeat: str = Form("")
    ) -> Response:
        if ctx.auth.configured:
            return RedirectResponse("/login", status_code=303)
        who = request.state.client
        wait = ctx.auth.throttle.retry_after(who)
        error = ""
        if wait:
            error = f"Zu viele Versuche. Bitte {wait} Sekunden warten."
        elif password != repeat:
            error = "Die beiden Passwörter stimmen nicht überein."
        else:
            try:
                ctx.auth.setup(code, password)
            except PermissionError:
                ctx.auth.throttle.failed(who)
                error = "Der Code stimmt nicht. Er steht im Protokoll des Servers."
            except PasswordRejected as exc:
                error = text.PASSWORD[exc.args[0]].format(min=MIN_PASSWORD)
        if error:
            return page(request, "setup.html", error=error, min_password=MIN_PASSWORD)
        token = ctx.auth.login(password, who, request.headers.get("user-agent", ""))
        response = RedirectResponse("/settings?welcome=1", status_code=303)
        security.set_session_cookie(response, token or "", request.state.secure)
        return response

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> Response:
        if not ctx.auth.configured:
            return RedirectResponse("/setup", status_code=303)
        if ctx.auth.check(request.cookies.get(security.COOKIE, "")):
            return RedirectResponse("/", status_code=303)
        return page(request, "login.html", error="", insecure=_insecure(request))

    @app.post("/login")
    async def login(request: Request, password: str = Form("")) -> Response:
        who = request.state.client
        wait = ctx.auth.throttle.retry_after(who)
        if wait:
            response = page(
                request,
                "login.html",
                insecure=_insecure(request),
                error=f"Zu viele Versuche. Bitte {wait} Sekunden warten.",
            )
            response.status_code = 429
            response.headers["Retry-After"] = str(wait)
            return response
        token = ctx.auth.login(password, who, request.headers.get("user-agent", ""))
        if not token:
            response = page(request, "login.html", insecure=_insecure(request), error="Das Passwort stimmt nicht.")
            response.status_code = 401
            return response
        response = RedirectResponse("/", status_code=303)
        security.set_session_cookie(response, token, request.state.secure)
        return response

    @app.post("/logout")
    async def logout(request: Request) -> Response:
        ctx.auth.logout(request.state.session)
        response = RedirectResponse("/login", status_code=303)
        security.clear_session_cookie(response)
        return response

    def _insecure(request: Request) -> bool:
        """The password is about to cross a network unencrypted."""
        name = security.host(request, settings.trust_proxy).rsplit(":", 1)[0]
        return not request.state.secure and name not in ("localhost", "127.0.0.1", "[::1]")

    # -- pages -----------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, f: str = "all") -> HTMLResponse:
        if f not in text.FILTERS:
            f = "all"
        counts = db.count_by_state()
        filters = [
            {"id": k, "name": name, "n": sum(counts.get(s, 0) for s in states), "active": k == f}
            for k, (name, states) in text.FILTERS.items()
        ]
        items = db.items(text.FILTERS[f][1])
        return page(
            request,
            "index.html",
            items=items,
            filters=filters,
            f=f,
            takings=db.takings(),
            provider_ready=ctx.provider_ready(),
        )

    @app.get("/new", response_class=HTMLResponse)
    async def new(request: Request) -> HTMLResponse:
        return page(
            request,
            "new.html",
            max_photos=settings.max_photos,
            recent=db.items()[:4],
            provider_ready=ctx.provider_ready(),
        )

    @app.get("/items/{item_id}", response_class=HTMLResponse)
    async def item_page(request: Request, item_id: int) -> HTMLResponse:
        item = item_or_404(item_id)
        for photo in item["photos"]:
            # Which looks exist as files already: switching to those is instant.
            p = imaging.paths(settings.photo_dir, photo["file"])
            photo["looks"] = [k for k in imaging.EDITED_LOOKS if p[f"{k}_t"].is_file()]
        user_settings = db.settings()
        return page(
            request,
            "item.html",
            item=item,
            d=item["data"],
            v=item["suggestion"],
            platforms=market.platforms(item["data"], user_settings),
            changed=changed_fields(item),
            in_progress=in_progress(item),
            writing=item["status"] in ("queued", "writing"),
            look=item["photos"][0]["look"] if item["photos"] else "studio",
            checked=item["data"].get("checked") or [],
            cutout=ctx.cutout,
            fill_helper=user_settings["fill_helper"] == "1",
        )

    @app.get("/items/{item_id}/photos", response_class=HTMLResponse)
    async def photos_page(request: Request, item_id: int) -> HTMLResponse:
        return page(request, "photos.html", item=item_or_404(item_id))

    @app.get("/stats", response_class=HTMLResponse)
    async def stats_page(request: Request) -> HTMLResponse:
        return page(request, "stats.html", st=stats.compute(db.items()))

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(
        request: Request, saved: bool = False, welcome: bool = False, error: str = ""
    ) -> HTMLResponse:
        config = ctx.provider_config()
        return page(
            request,
            "settings.html",
            s=db.settings(),
            saved=saved,
            welcome=welcome,
            error=error,
            config=config,
            key_hint=SecretsStore.hint(config["api_key"]),
            locked={k: bool(getattr(settings, k)) for k in ("provider", "model", "base_url", "api_key")},
            providers=providers.PROVIDERS,
            provider_text=text.PROVIDERS,
            provider_ready=ctx.provider_ready(),
            provider_problem=text.MISSING.get(ctx.provider_missing() or "", ""),
            cutout=ctx.cutout,
            cutout_model=settings.cutout_model,
            min_password=MIN_PASSWORD,
            sessions=len(db.sessions("browser")),
            insecure=_insecure(request),
        )

    @app.post("/settings")
    async def save_settings(request: Request) -> RedirectResponse:
        form = await request.form()
        values = {k: str(v) for k, v in form.items()}
        values["negotiable"] = "1" if values.get("negotiable") else "0"
        if values.get("look") not in LOOKS:
            values.pop("look", None)
        for key in ("provider", "model", "model_distractors", "base_url", "fill_helper"):
            values.pop(key, None)  # these have their own forms
        db.save_settings(values)
        return RedirectResponse("/settings?saved=1", status_code=303)

    @app.post("/settings/provider")
    async def save_provider(
        provider: str = Form(""),
        model: str = Form(""),
        model_distractors: str = Form(""),
        base_url: str = Form(""),
        api_key: str = Form(""),
    ) -> RedirectResponse:
        if provider and provider not in providers.PROVIDERS:
            raise fail(400, "bad_choice")
        if base_url and not base_url.startswith(("http://", "https://")):
            raise fail(400, "link_scheme")
        previous = db.settings()["provider"]
        db.save_settings(
            {"provider": provider, "model": model, "model_distractors": model_distractors, "base_url": base_url}
        )
        if api_key.strip():
            ctx.secrets.set("api_key", api_key.strip())
        elif provider != previous:
            # A key belongs to one provider. Sending the old one to a new
            # address would hand it to someone it was not issued by.
            ctx.secrets.set("api_key", "")
        return RedirectResponse("/settings?saved=1#ai", status_code=303)

    @app.post("/settings/provider/test")
    def test_provider() -> dict[str, Any]:
        """One real, tiny request, so a wrong key shows up here and not on
        the first listing. Runs in a thread: it waits on the network."""
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
        try:
            answer = ctx.provider().ask(
                'Antworte mit {"ok": true}.', system="Du antwortest nur mit JSON.", schema=schema, images=[]
            )
        except providers.ProviderError as exc:
            log.warning("Provider test failed: %s", exc)
            return {"ok": False, "message": text.ERRORS.get(exc.code, text.ERRORS["failed"]), "detail": str(exc)[:300]}
        return {"ok": True, "model": text.model_name(answer.model)}

    @app.post("/settings/password")
    async def change_password(
        request: Request, current: str = Form(""), new: str = Form(""), repeat: str = Form("")
    ) -> RedirectResponse:
        who = request.state.client
        if ctx.auth.throttle.retry_after(who):
            return RedirectResponse("/settings?error=wait#access", status_code=303)
        if new != repeat:
            return RedirectResponse("/settings?error=mismatch#access", status_code=303)
        try:
            ok = ctx.auth.change_password(current, new, keep=request.state.session)
        except PasswordRejected as exc:
            return RedirectResponse(f"/settings?error={exc.args[0]}#access", status_code=303)
        if not ok:
            ctx.auth.throttle.failed(who)
            return RedirectResponse("/settings?error=wrong#access", status_code=303)
        return RedirectResponse("/settings?saved=1#access", status_code=303)

    @app.post("/settings/sign-out-everywhere")
    async def sign_out_everywhere() -> Response:
        ctx.auth.logout_everywhere()
        response = RedirectResponse("/login", status_code=303)
        security.clear_session_cookie(response)
        return response

    @app.post("/settings/fill-helper")
    async def fill_helper_switch(enable: str = Form("")) -> RedirectResponse:
        on = enable == "1"
        db.save_settings({"fill_helper": "1" if on else "0"})
        if not on:
            # Switching it off also cuts off every installed copy.
            ctx.auth.revoke_helper()
        return RedirectResponse("/fill-helper" if on else "/settings?saved=1", status_code=303)

    @app.get("/export.zip")
    def export() -> Response:
        """Everything a person stored: the database and the original photos.
        Edited looks are left out, they can be produced again; so is the
        file with the API key."""
        buffer = io.BytesIO()
        copy = settings.data_dir / "export.tmp"
        try:
            db.backup(copy)
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as z:
                z.write(copy, "troedel.db")
                for item in db.items():
                    for photo in item["photos"]:
                        path = imaging.paths(settings.photo_dir, photo["file"])["original"]
                        if path.is_file():
                            z.write(path, f"photos/{path.name}")
        finally:
            copy.unlink(missing_ok=True)
        return Response(
            buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="troedel-export.zip"'},
        )

    # -- photos ----------------------------------------------------------------

    @app.get("/photo/{name}")
    async def photo(name: str) -> FileResponse:
        if not PHOTO_NAME.match(name):
            raise HTTPException(404)
        path = settings.photo_dir / name
        if not path.is_file():
            raise HTTPException(404)
        # Not "immutable": producing a look again writes it under the same
        # name. With no-cache the browser asks and usually gets a 304.
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-cache"})

    @app.get("/items/{item_id}/photos.zip")
    async def photos_zip(item_id: int) -> Response:
        item = item_or_404(item_id)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as z:
            for i, p in enumerate(item["photos"], 1):
                name = photo_url(p).removeprefix("/photo/").split("?")[0]
                z.write(settings.photo_dir / name, f"{item_id}-{i}.jpg")
        return Response(
            buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="troedel-{item_id}.zip"'},
        )

    async def take_photos(item_id: int, files: list[UploadFile]) -> list[int]:
        existing = db.photos(item_id)
        if len(existing) + len(files) > settings.max_photos:
            raise fail(413, "too_many_photos", n=settings.max_photos)
        look = db.settings().get("look", "studio") if ctx.cutout else "original"
        if look not in LOOKS:
            look = "studio"
        if existing:
            # New photos of an existing item get that item's look.
            look = existing[0]["look"]
        added, stored = [], []
        try:
            for file in files:
                data = await file.read(security.MAX_PHOTO_BYTES + 1)
                if len(data) > security.MAX_PHOTO_BYTES:
                    raise fail(413, "photo_too_large", mb=security.MAX_PHOTO_BYTES >> 20)
                try:
                    image = imaging.read(data)
                except imaging.ImageError as exc:
                    raise fail(400, "not_an_image") from exc
                name = imaging.store(image, settings.photo_dir)
                stored.append(name)
                added.append(db.add_photo(item_id, name, look))
        except HTTPException:
            # All or nothing: a half-added batch would be hard to explain.
            for photo_id in added:
                db.delete_photo(photo_id)
            for name in stored:
                imaging.delete(settings.photo_dir, name)
            raise
        return added

    # -- API: items --------------------------------------------------------------

    @app.post("/api/items")
    async def api_new(
        photos: list[UploadFile] = File(...), keywords: str = Form(""), product: str = Form("")
    ) -> JSONResponse:
        if not photos:
            raise fail(400, "need_photo")
        if len(photos) > settings.max_photos:
            raise fail(413, "too_many_photos", n=settings.max_photos)
        item_id = db.add_item(keywords[:500], product[:200])
        try:
            added = await take_photos(item_id, photos)
        except HTTPException:
            db.delete_item(item_id)
            raise
        ctx.worker.write(item_id)
        for photo_id in added:
            ctx.worker.edit(photo_id)
        return JSONResponse({"id": item_id}, status_code=201)

    @app.get("/api/items/{item_id}")
    async def api_item(item_id: int) -> dict[str, Any]:
        return summary(item_or_404(item_id))

    @app.get("/api/status")
    async def api_status(ids: str = "") -> dict[str, Any]:
        """Short state of several items, for the list while work is going on."""
        out = {}
        for part in ids.split(",")[:200]:
            if part.strip().isdigit() and (item := db.item(int(part))):
                out[part.strip()] = {"status": item["status"], "in_progress": in_progress(item)}
        return out

    @app.patch("/api/items/{item_id}")
    async def api_change(item_id: int, change: Change) -> dict[str, Any]:
        item = item_or_404(item_id)
        fields: dict[str, Any] = {}
        for key, value in change.data.items():
            kind = EDITABLE.get(key)
            if kind is None:
                raise fail(400, "unknown_field", field=key)
            if kind is int:
                try:
                    fields[key] = int(str(value).replace(market.CURRENCY, "").strip() or 0)
                except ValueError as exc:
                    raise fail(400, "price_number") from exc
            elif key == "checked":
                fields[key] = [str(x) for x in (value if isinstance(value, list) else [])][:50]
            elif kind is list:
                lines = value if isinstance(value, list) else str(value).splitlines()
                fields[key] = [str(x).strip().lstrip("•-– ").strip() for x in lines if str(x).strip()]
            elif key == "condition" and value not in listing.CONDITIONS:
                raise fail(400, "bad_choice")
            elif key == "shipping" and value not in listing.SHIPPING:
                raise fail(400, "bad_choice")
            else:
                fields[key] = str(value).strip()
        if fields:
            db.update_data(item_id, fields)
        if change.status:
            if change.status not in MANUAL:
                raise fail(400, "bad_state")
            not_busy(item)
            if change.status == "sold" and item["status"] != "sold":
                price = db.item(item_id)["data"].get("price")  # type: ignore[index]
                db.mark_sold(item_id, price if isinstance(price, int) else None, "")
            else:
                db.set_state(item_id, change.status)
        return summary(item_or_404(item_id))

    @app.post("/api/items/{item_id}/sold")
    async def api_sold(item_id: int, sale: Sale) -> dict[str, Any]:
        not_busy(item_or_404(item_id))
        if sale.via and sale.via not in sold_via:
            raise fail(400, "bad_choice")
        amount = sale.price.replace(market.CURRENCY, "").replace(",", ".").strip()
        try:
            price = round(float(amount)) if amount else None
        except (ValueError, OverflowError) as exc:
            raise fail(400, "amount_number") from exc
        if price is not None and price < 0:
            raise fail(400, "amount_number")
        db.mark_sold(item_id, price, sale.via)
        return summary(item_or_404(item_id))

    @app.post("/api/items/{item_id}/rewrite")
    async def api_rewrite(item_id: int, body: Note) -> dict[str, Any]:
        """Write the listing from scratch, discarding edits."""
        not_busy(item_or_404(item_id))
        db.set_note(item_id, body.note[:1000])
        db.set_state(item_id, "queued")
        ctx.worker.write(item_id)
        return summary(item_or_404(item_id))

    @app.post("/api/items/{item_id}/revise")
    async def api_revise(item_id: int, body: Instruction) -> dict[str, Any]:
        """Rework the listing as instructed, and only as instructed."""
        item = item_or_404(item_id)
        not_busy(item)
        if not item["data"].get("title"):
            raise fail(409, "nothing_to_revise")
        if not body.instruction.strip():
            raise fail(400, "what_to_change")
        db.request_revision(item_id, body.instruction[:1000])
        ctx.worker.write(item_id)
        return summary(item_or_404(item_id))

    @app.post("/api/items/{item_id}/undo")
    async def api_undo(item_id: int) -> dict[str, Any]:
        item_or_404(item_id)
        if not db.undo_revision(item_id):
            raise fail(409, "nothing_to_undo")
        return summary(item_or_404(item_id))

    @app.post("/api/items/{item_id}/keep")
    async def api_keep(item_id: int) -> dict[str, Any]:
        item_or_404(item_id)
        db.keep_revision(item_id)
        return summary(item_or_404(item_id))

    @app.delete("/api/items/{item_id}")
    async def api_delete(item_id: int) -> dict[str, Any]:
        item_or_404(item_id)
        for name in db.delete_item(item_id):
            imaging.delete(settings.photo_dir, name)
        return {"ok": True}

    # -- API: photos -------------------------------------------------------------

    @app.post("/api/items/{item_id}/photos")
    async def api_add_photos(item_id: int, photos: list[UploadFile] = File(...)) -> dict[str, Any]:
        item_or_404(item_id)
        for photo_id in await take_photos(item_id, photos):
            ctx.worker.edit(photo_id)
        return summary(item_or_404(item_id))

    @app.post("/api/items/{item_id}/look")
    async def api_look(item_id: int, body: LookChoice) -> dict[str, Any]:
        """Produce all photos of an item in one look. A look that already
        exists is there at once."""
        item = item_or_404(item_id)
        if body.look not in LOOKS:
            raise fail(400, "bad_choice")
        if body.look != "original" and not ctx.cutout:
            raise fail(409, "editing_off")
        for p in item["photos"]:
            if body.again and body.look != "original":
                imaging.discard_look(settings.photo_dir, p["file"], body.look)
                if body.look == "tidy":
                    db.forget_distractors(p["id"])
            db.order_look(p["id"], body.look)
            if body.look != "original":
                ctx.worker.edit(p["id"])
        return summary(item_or_404(item_id))

    @app.patch("/api/photos/{photo_id}")
    async def api_photo(photo_id: int, body: PhotoChange) -> dict[str, Any]:
        p = db.photo(photo_id)
        if not p:
            raise HTTPException(404)
        if body.shown:
            if body.shown not in ("original", p["look"]):
                raise fail(400, "bad_choice")
            if body.shown != "original" and p["state"] != "done":
                raise fail(409, "not_edited_yet")
            db.show(photo_id, body.shown)
        if body.move in (-1, 1):
            db.move_photo(photo_id, body.move)
        if body.retry and p["state"] == "failed" and ctx.cutout:
            db.set_photo_state(photo_id, "pending")
            ctx.worker.edit(photo_id)
        return summary(item_or_404(p["item_id"]))

    @app.delete("/api/photos/{photo_id}")
    async def api_delete_photo(photo_id: int) -> dict[str, Any]:
        p = db.photo(photo_id)
        if not p:
            raise HTTPException(404)
        if len(db.photos(p["item_id"])) <= 1:
            raise fail(409, "last_photo")
        name = db.delete_photo(photo_id)
        if name:
            imaging.delete(settings.photo_dir, name)
        return summary(item_or_404(p["item_id"]))

    # -- API: where it is listed -------------------------------------------------

    def mark_listed(item_id: int, platform: str, url: str) -> dict[str, Any]:
        item_or_404(item_id)
        if platform not in market.NAMES:
            raise fail(400, "unknown_platform")
        if url and not url.startswith(("http://", "https://")):
            raise fail(400, "link_scheme")
        db.set_listed(item_id, platform, url[:500])
        return summary(item_or_404(item_id))

    @app.put("/api/items/{item_id}/listed/{platform}")
    async def api_listed(item_id: int, platform: str, body: Link) -> dict[str, Any]:
        return mark_listed(item_id, platform, body.url)

    @app.delete("/api/items/{item_id}/listed/{platform}")
    async def api_unlisted(item_id: int, platform: str) -> dict[str, Any]:
        item_or_404(item_id)
        db.set_unlisted(item_id, platform)
        return summary(item_or_404(item_id))

    # -- fill helper (userscript) ------------------------------------------------
    # The helper runs on the marketplace's page and fills in the form there.
    # It reads through these three routes with its own token and can do one
    # thing besides reading: note that an item is now listed.

    def base(request: Request) -> str:
        """The address under which this browser reached Trödel; the
        userscript will use the same one."""
        return f"{security.scheme(request, settings.trust_proxy)}://{security.host(request, settings.trust_proxy)}"

    def helper_on() -> None:
        if db.settings()["fill_helper"] != "1":
            raise fail(404, "helper_off")

    @app.get("/api/helper/items")
    async def helper_items(request: Request) -> dict[str, Any]:
        helper_on()
        b = base(request)
        return {
            "items": [
                {
                    "id": i["id"],
                    "title": i["data"].get("title") or i["keywords"],
                    "price": i["data"].get("price"),
                    "thumb": b + cover(i) if i["photos"] else "",
                    "listed": list(i["listings"]),
                }
                for i in db.items(("draft", "online"))
            ]
        }

    @app.get("/api/helper/items/{item_id}")
    async def helper_item(request: Request, item_id: int, platform: str) -> dict[str, Any]:
        helper_on()
        item = item_or_404(item_id)
        user_settings = db.settings()
        p = next((x for x in market.platforms(item["data"], user_settings) if x.id == platform), None)
        if p is None:
            raise fail(400, "unknown_platform")
        b = base(request)
        return {
            "id": item["id"],
            "platform": platform,
            "title": p.value("title"),
            "description": p.value("description"),
            "price": item["data"].get("price"),
            "negotiable": user_settings.get("negotiable") == "1",
            "fields": [{"key": f.key, "label": f.label, "value": f.value, "hint": f.hint} for f in p.fields],
            "photos": [b + photo_url(x) for x in item["photos"]],
            "thumb": b + cover(item) if item["photos"] else "",
            "listed": platform in item["listings"],
        }

    @app.put("/api/helper/items/{item_id}/listed/{platform}")
    async def helper_listed(item_id: int, platform: str, body: Link) -> dict[str, Any]:
        helper_on()
        return mark_listed(item_id, platform, body.url)

    @app.get("/fill-helper", response_class=HTMLResponse)
    async def fill_helper_page(request: Request, install: str = "") -> HTMLResponse:
        _token, until = installs.get(install, ("", 0.0))
        return page(
            request,
            "fill_helper.html",
            base=base(request),
            enabled=db.settings()["fill_helper"] == "1",
            installed=ctx.auth.helper_count(),
            # A script made a moment ago, waiting to be installed.
            script=f"/troedel.user.js?install={install}" if until > time.monotonic() else "",
        )

    @app.post("/fill-helper/install")
    async def fill_helper_install(request: Request) -> RedirectResponse:
        """Creates the token for one installation and hands it over through
        a short-lived install code. The token itself is stored only as a
        hash and only ever appears inside the script it was made for."""
        helper_on()
        now = time.monotonic()
        for code in [c for c, (_, until) in installs.items() if until < now]:
            del installs[code]
        code = secrets.token_urlsafe(24)
        token = ctx.auth.new_helper_token(request.headers.get("user-agent", ""))
        installs[code] = (token, now + INSTALL_SECONDS)
        # Back to the page, which then links to the script. Sending the
        # browser straight on to the script looked like nothing happened
        # with Tampermonkey in Chrome: it takes such a jump away from the
        # browser and then shows nothing. A link that is clicked it handles,
        # and a page can offer the address to paste when even that fails.
        return RedirectResponse(f"/fill-helper?install={code}#install", status_code=303)

    @app.get("/troedel.user.js")
    async def userscript(request: Request, install: str = "") -> Response:
        """The userscript for this instance. Served only against a valid
        install code, which is why the path needs no session: userscript
        managers fetch the address again on their own, without the cookie.
        The code works for a few minutes, then the address is dead."""
        token, until = installs.get(install, ("", 0.0))
        if not token or until < time.monotonic() or db.settings()["fill_helper"] != "1":
            raise HTTPException(404)
        source = (HERE / "static" / "troedel.user.js").read_text(encoding="utf-8")
        script = (
            source.replace("__BASE__", base(request))
            .replace("__VERSION__", __version__)
            .replace("__HOST__", security.host(request, settings.trust_proxy).rsplit(":", 1)[0])
            .replace("__TOKEN__", token)
        )
        return Response(script, media_type="text/javascript; charset=utf-8")

    # -- operations --------------------------------------------------------------

    @app.get("/health")
    async def health() -> dict[str, str]:
        """For container health checks. Says nothing about what is stored:
        this route needs no login."""
        return {"status": "ok"}

    @app.get("/manifest.webmanifest")
    async def manifest() -> JSONResponse:
        return JSONResponse(
            {
                "name": "Trödel",
                "short_name": "Trödel",
                "description": "Foto rein, Verkaufsanzeige raus.",
                "start_url": "/",
                "scope": "/",
                "display": "standalone",
                "background_color": "#f2f6f8",
                "theme_color": "#f2f6f8",
                "icons": [
                    {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
                    {
                        "src": "/static/icons/icon-512.png",
                        "sizes": "512x512",
                        "type": "image/png",
                        "purpose": "maskable",
                    },
                ],
            },
            media_type="application/manifest+json",
        )

    return app
