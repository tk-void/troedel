"""What every request passes before it reaches a route.

1. Nothing but the login, the first-run setup, the health check and the
   static files is served without a valid session. The check lives here,
   in one place, so a new route is protected without anyone remembering to.
2. Requests that change something must come from Trödel's own pages: the
   ``Origin`` header has to match the host. A session cookie alone is not
   enough, otherwise any website open in the same browser could act with it.
3. The fill helper authenticates with its own bearer token and reaches only
   the paths listed for it.
4. Every response gets headers that keep the page from being framed, from
   loading foreign scripts and from being cached with someone's listings.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from ..auth import Auth
from . import text

COOKIE = "troedel_session"
COOKIE_MAX_AGE = 30 * 24 * 3600
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

PUBLIC_PATHS = {"/login", "/setup", "/health", "/manifest.webmanifest", "/troedel.user.js"}
"""The userscript is public as a path only: it is served solely against a
short-lived install code, see ``app.userscript``."""
PUBLIC_PREFIXES = ("/static/",)
HELPER_PREFIXES = ("/api/helper/", "/photo/")
"""What the fill helper's token may reach: its own small API and the photos
it has to upload to the marketplace."""

MAX_PHOTO_BYTES = 30 * 1024 * 1024


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def scheme(request: Request, trust_proxy: bool) -> str:
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
        if forwarded in ("http", "https"):
            return forwarded
    return request.url.scheme


def host(request: Request, trust_proxy: bool) -> str:
    if trust_proxy and request.headers.get("x-forwarded-host"):
        return request.headers["x-forwarded-host"].split(",")[0].strip().lower()
    return request.headers.get("host", "").lower()


def client(request: Request, trust_proxy: bool) -> str:
    """Who is asking, for the login throttle. The forwarded address is only
    believed behind a proxy, and then the last entry: that is the one the
    proxy itself appended, the ones before it are whatever the client sent."""
    if trust_proxy:
        forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if forwarded:
            return forwarded[-1]
    return request.client.host if request.client else "unknown"


def same_origin(request: Request, trust_proxy: bool) -> bool:
    """True if a state-changing request was sent by a page of this app."""
    site = request.headers.get("sec-fetch-site")
    if site and site not in ("same-origin", "none"):
        return False
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        # Browsers send Origin with every POST from a page. A request with
        # neither header is not from a page of ours.
        return False
    parts = urlsplit(source)
    return parts.netloc.lower() == host(request, trust_proxy) and parts.scheme in ("http", "https")


def bearer(request: Request) -> str:
    value = request.headers.get("authorization", "")
    return value[7:].strip() if value[:7].lower() == "bearer " else ""


def set_session_cookie(response: Response, token: str, secure: bool) -> None:
    response.set_cookie(COOKIE, token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", secure=secure, path="/")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def _wants_page(request: Request) -> bool:
    return (
        request.method == "GET"
        and not request.url.path.startswith("/api/")
        and "text/html" in request.headers.get("accept", "")
    )


def install(app, auth: Auth, trust_proxy: bool, max_body: int, helper_enabled) -> None:
    """``helper_enabled`` is a callable, because the helper is switched on
    and off in the settings while the app runs."""

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        request.state.nonce = secrets.token_urlsafe(16)
        request.state.secure = scheme(request, trust_proxy) == "https"
        request.state.client = client(request, trust_proxy)
        request.state.session = ""
        response = await _decide(request, call_next, path)
        _harden(response, request, path)
        return response

    async def _decide(request: Request, call_next, path: str) -> Response:
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > max_body:
            return JSONResponse(
                {"detail": text.API["photo_too_large"].format(mb=MAX_PHOTO_BYTES >> 20)}, status_code=413
            )

        token = bearer(request)
        if token:
            # A bearer token is not sent by a browser on its own, so it
            # needs no origin check, but it is confined to its paths.
            if helper_enabled() and path.startswith(HELPER_PREFIXES) and auth.check_helper(token):
                request.state.helper = True
                return await call_next(request)
            return JSONResponse({"detail": text.API["login_required"]}, status_code=401)

        if request.method not in SAFE_METHODS and not same_origin(request, trust_proxy):
            return JSONResponse({"detail": text.API["forbidden"]}, status_code=403)

        if is_public(path):
            return await call_next(request)

        if not auth.configured:
            if _wants_page(request):
                return RedirectResponse("/setup", status_code=303)
            return JSONResponse({"detail": text.API["login_required"]}, status_code=401)

        session = request.cookies.get(COOKIE, "")
        if auth.check(session):
            request.state.session = session
            return await call_next(request)

        if _wants_page(request):
            return RedirectResponse("/login", status_code=303)
        return JSONResponse({"detail": text.API["login_required"]}, status_code=401)

    def _harden(response: Response, request: Request, path: str) -> None:
        nonce = request.state.nonce
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if request.state.secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        # Pages and API never from a cache: a stale list is confusing, and
        # a shared computer should not keep someone's listings. Photos and
        # static files set their own headers.
        if not path.startswith(("/photo/", "/static/")):
            response.headers["Cache-Control"] = "no-store"
