"""The small window of the downloads: ``troedel window``.

Someone who double-clicks an icon has no terminal. Everything the terminal
used to say has to be in a window instead: that Trödel is running, where to
open it, the setup code of the first start, and how to reach it from a
phone. Closing the window is what stops Trödel.

Two halves. ``Server`` runs the web app in a thread and knows nothing about
windows, so it can be tested anywhere. ``Window`` is Tk, because Tk comes
with Python: no further dependency, and no browser engine to ship. The QR
code for the phone is drawn only if ``segno`` is installed (extra
``desktop``).
"""

from __future__ import annotations

import json
import logging
import socket
import sys
import threading
import urllib.request
import webbrowser
from collections.abc import Callable
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from . import __version__
from .cli import lan_address
from .config import Settings

log = logging.getLogger("troedel.desktop")

STATIC = Path(__file__).resolve().parent / "web" / "static"

T = {
    "starting": "Startet …",
    "running": "Läuft",
    "failed": "Nicht gestartet",
    "elsewhere": "Läuft bereits",
    "here": "Auf diesem Computer",
    "open": "Im Browser öffnen",
    "code": "Einrichtungscode",
    "code_hint": "Erster Start: Diesen Code im Browser eintippen und ein Passwort wählen.",
    "copy": "Kopieren",
    "copied": "Kopiert",
    "phone": "Auf dem Handy",
    "share": "Im Heimnetz freigeben",
    "share_off": (
        "Einschalten, um Trödel auch vom Handy oder Tablet aus zu benutzen. "
        "Nur im eigenen WLAN einschalten, nicht in einem fremden oder öffentlichen."
    ),
    "share_steps": (
        "1. Das Handy muss im selben WLAN sein wie dieser Computer.\n"
        "2. Mit der Kamera den Code scannen oder die Adresse im Browser eintippen.\n"
        "3. iPhone: in Safari „Teilen“ und „Zum Home-Bildschirm“. "
        "Android: im Menü „Zum Startbildschirm hinzufügen“. "
        "Dann liegt Trödel wie eine App auf dem Handy."
    ),
    "share_steps_no_qr": (
        "1. Das Handy muss im selben WLAN sein wie dieser Computer.\n"
        "2. Diese Adresse im Browser des Handys eintippen.\n"
        "3. iPhone: in Safari „Teilen“ und „Zum Home-Bildschirm“. "
        "Android: im Menü „Zum Startbildschirm hinzufügen“. "
        "Dann liegt Trödel wie eine App auf dem Handy."
    ),
    "share_firewall": "Fragt der Computer, ob Verbindungen aus dem Netzwerk erlaubt sind: für das Heimnetz erlauben.",
    "no_network": "Dieser Computer ist gerade in keinem Netzwerk.",
    "footer": "Trödel läuft, solange dieses Fenster offen ist.",
    "quit": "Beenden",
    "data": "Deine Daten",
    "data_hint": "Anzeigen, Fotos und Einstellungen. Zum Sichern diesen Ordner kopieren.",
    "show": "Ordner öffnen",
    "port_busy": (
        "Der Anschluss {port} ist von einem anderen Programm belegt. "
        "Das andere Programm beenden und Trödel neu starten."
    ),
    "elsewhere_hint": "Trödel ist schon geöffnet, in einem anderen Fenster. Dieses hier kann geschlossen werden.",
    "broken": "Trödel konnte nicht starten. Einzelheiten stehen in:\n{log}",
    "no_tk": "troedel: this Python comes without Tk, so there is no window. Start with: troedel --open",
}


def default_data_dir() -> Path:
    """Where a double-clicked Trödel keeps its data. Not next to the
    program: an installed copy may sit somewhere read-only, and a newer
    download must find the old listings."""
    return Path.home() / "Troedel"


class Server:
    """The web app in a thread, to be started, stopped and asked how it is.

    ``state`` is one of ``starting``, ``running``, ``failed`` and
    ``elsewhere`` (another Trödel already answers on the port: the usual
    result of a second double-click, and not an error)."""

    def __init__(self, settings: Settings, make_app: Callable[[Settings], Any] | None = None) -> None:
        self.settings = settings
        self.lan = False
        self.error = ""
        self._make_app = make_app
        self._uvicorn: Any = None
        self._thread: threading.Thread | None = None
        self._app: Any = None
        self._elsewhere = False
        self._switching = threading.RLock()

    # -- what the window shows -------------------------------------------------

    @property
    def state(self) -> str:
        if self._elsewhere:
            return "elsewhere"
        if self.error:
            return "failed"
        if self._uvicorn is not None and self._uvicorn.started and self._thread and self._thread.is_alive():
            return "running"
        return "starting"

    @property
    def url(self) -> str:
        return f"http://localhost:{self.settings.port}"

    @property
    def phone_url(self) -> str:
        """The address for other devices; empty while not shared or while
        this machine has no network."""
        if not self.lan or self.state != "running":
            return ""
        address = lan_address()
        return f"http://{address}:{self.settings.port}" if address else ""

    @property
    def setup_code(self) -> str:
        """The code of the first start; empty as soon as a password exists."""
        if self._app is None or self.state != "running":
            return ""
        return self._app.state.ctx.auth.setup_code

    # -- running ---------------------------------------------------------------

    def start(self, lan: bool) -> None:
        self.lan = lan
        self.error = ""
        self._elsewhere = False
        host = "0.0.0.0" if lan else "127.0.0.1"  # noqa: S104 - the user ticked "share in the home network"
        port = self.settings.port
        if _taken(host, port):
            # uvicorn would log this and call sys.exit, which in a thread
            # leaves a window that says "starting" forever.
            if _is_troedel(port):
                self._elsewhere = True
            else:
                self.error = T["port_busy"].format(port=port)
            return
        try:
            import uvicorn

            settings = replace(self.settings, host=host)
            self._app = (self._make_app or _create_app)(settings)
            self._uvicorn = uvicorn.Server(
                uvicorn.Config(
                    self._app, host=host, port=port, log_level="warning", proxy_headers=False, server_header=False
                )
            )
        except Exception:
            log.exception("could not set up the server")
            self.error = T["broken"].format(log=self.log_path)
            return
        self._thread = threading.Thread(target=self._serve, name="server", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        try:
            self._uvicorn.run()
        except BaseException:  # noqa: BLE001 - uvicorn leaves through SystemExit when it cannot start
            log.exception("the server stopped")
            self.error = T["broken"].format(log=self.log_path)

    def stop(self) -> None:
        # The lock: quitting while a switch is half done would otherwise
        # stop nothing and leave the new server running behind a closed window.
        with self._switching:
            if self._uvicorn is not None:
                self._uvicorn.should_exit = True
            if self._thread is not None:
                self._thread.join(15)
            self._uvicorn = self._thread = self._app = None

    def switch(self, lan: bool) -> None:
        """(Re)start listening, for the network or for this computer only,
        without blocking the caller: loading the app takes a moment, and
        stopping waits for running requests."""

        def work() -> None:
            with self._switching:
                self.stop()
                self.start(lan)

        threading.Thread(target=work, name="switch", daemon=True).start()

    @property
    def log_path(self) -> Path:
        return self.settings.data_dir / "troedel.log"


def _create_app(settings: Settings) -> Any:
    from .web.app import create_app

    return create_app(settings)


def _taken(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # As the server itself binds. Without it, a port just given up
        # (switching the network share) counts as taken for a minute on
        # Linux and macOS. On Windows the same option would let us bind a
        # port that is in use, and nothing lingers there anyway.
        if sys.platform != "win32":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            return True
    return False


def _is_troedel(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:  # noqa: S310
            return json.loads(response.read()) == {"status": "ok"}
    except (OSError, ValueError):
        return False


# -- remembering the switch ------------------------------------------------------


def remembered(settings: Settings) -> bool:
    """Whether Trödel was shared in the home network the last time. Without
    a remembered choice, the configured address decides."""
    try:
        return bool(json.loads((settings.data_dir / "window.json").read_text(encoding="utf-8"))["lan"])
    except (OSError, ValueError, KeyError, TypeError):
        return settings.host not in ("127.0.0.1", "localhost", "::1")


def remember(settings: Settings, lan: bool) -> None:
    try:
        (settings.data_dir / "window.json").write_text(json.dumps({"lan": lan}), encoding="utf-8")
    except OSError:
        log.warning("could not remember the network switch")


# -- the window ------------------------------------------------------------------

GREEN, CREAM, RUST, INK, MUTED = "#1F4A3D", "#F6F2EA", "#C65D3B", "#22302B", "#6B746F"
DOT = {"starting": "#C9A227", "running": "#2E8B57", "failed": RUST, "elsewhere": "#2E8B57"}


class Window:
    def __init__(self, server: Server, browser: Callable[[str], Any] = webbrowser.open) -> None:
        import tkinter as tk
        from tkinter import font, ttk

        self.tk, self.ttk = tk, ttk
        self.server = server
        self.browser = browser
        self.opened = False
        self.shown: tuple[Any, ...] = ()

        _crisp_on_windows()
        root = self.root = tk.Tk(className="Troedel")
        root.title("Trödel")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.scale = root.winfo_fpixels("1i") / 96
        self.logo = self._logo()
        if self.logo is not None:
            root.iconphoto(True, tk.PhotoImage(file=str(STATIC / "icons" / "icon-192.png")))

        base = font.nametofont("TkDefaultFont")
        size = abs(base.actual("size")) or 10
        self.fonts = {
            "title": base.copy(),
            "head": base.copy(),
            "code": font.nametofont("TkFixedFont").copy(),
            "link": base.copy(),
        }
        self.fonts["title"].configure(size=round(size * 1.9), weight="bold")
        self.fonts["head"].configure(weight="bold")
        self.fonts["code"].configure(size=round(size * 1.7), weight="bold")
        self.fonts["link"].configure(underline=True)

        style = ttk.Style(root)
        self.native = style.theme_use() == "aqua"
        # macOS draws its own window background and ignores ours; everywhere
        # else the grey default looks like a dialog from 1998.
        self.bg = style.lookup("TFrame", "background") if self.native else CREAM
        if not self.native:
            root.configure(background=CREAM)
            style.configure(".", background=CREAM, foreground=INK)
            style.configure("TCheckbutton", background=CREAM)
        style.configure("Muted.TLabel", foreground=MUTED)

        wrap = self.wrap = round(380 * self.scale)
        pad = round(18 * self.scale)
        body = ttk.Frame(root, padding=pad)
        body.grid(sticky="nsew")

        head = ttk.Frame(body)
        head.grid(sticky="w")
        if self.logo is not None:
            ttk.Label(head, image=self.logo).grid(row=0, column=0, rowspan=2, padx=(0, round(12 * self.scale)))
        ttk.Label(head, text="Trödel", font=self.fonts["title"]).grid(row=0, column=1, sticky="w")
        status = ttk.Frame(head)
        status.grid(row=1, column=1, sticky="w")
        self.dot = tk.Canvas(status, width=12, height=12, highlightthickness=0, background=self.bg)
        self.dot.grid(row=0, column=0, padx=(0, 6))
        self.dot_item = self.dot.create_oval(2, 2, 11, 11, outline="", fill=DOT["starting"])
        self.status = ttk.Label(status, text=T["starting"])
        self.status.grid(row=0, column=1)

        self.message = ttk.Label(body, wraplength=wrap, justify="left")

        self.here = self._section(body, T["here"])
        self.link = ttk.Label(self.here, text=server.url, font=self.fonts["link"], foreground="#1A5FB4", cursor="hand2")
        self.link.grid(row=1, column=0, sticky="w")
        self.link.bind("<Button-1>", lambda e: self.open())
        self.open_button = ttk.Button(self.here, text=T["open"], command=self.open, state="disabled")
        self.open_button.grid(row=1, column=1, sticky="e", padx=(pad, 0))
        self.here.columnconfigure(0, weight=1)

        self.code = self._section(body, T["code"])
        self.code_text = ttk.Label(self.code, font=self.fonts["code"])
        self.code_text.grid(row=1, column=0, sticky="w")
        self.copy_button = ttk.Button(self.code, text=T["copy"], command=self.copy)
        self.copy_button.grid(row=1, column=1, sticky="e", padx=(pad, 0))
        ttk.Label(self.code, text=T["code_hint"], wraplength=wrap, justify="left", style="Muted.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        self.code.columnconfigure(0, weight=1)

        self.phone = self._section(body, T["phone"])
        self.share = tk.BooleanVar(value=server.lan)
        self.share_box = ttk.Checkbutton(self.phone, text=T["share"], variable=self.share, command=self.toggle)
        self.share_box.grid(row=1, column=0, columnspan=2, sticky="w")
        self.phone_hint = ttk.Label(self.phone, wraplength=wrap, justify="left", style="Muted.TLabel")
        self.phone_hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.qr = tk.Canvas(self.phone, highlightthickness=0, background="white")
        self.phone_url = ttk.Label(self.phone, font=self.fonts["head"])
        self.phone_steps = ttk.Label(self.phone, justify="left")

        data = self._section(body, T["data"])
        ttk.Label(data, text=str(server.settings.data_dir), wraplength=wrap - round(120 * self.scale)).grid(
            row=1, column=0, sticky="w"
        )
        ttk.Button(data, text=T["show"], command=self.show_data).grid(row=1, column=1, sticky="e", padx=(pad, 0))
        ttk.Label(data, text=T["data_hint"], wraplength=wrap, justify="left", style="Muted.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        data.columnconfigure(0, weight=1)

        foot = ttk.Frame(body)
        foot.grid(sticky="ew", pady=(pad, 0))
        foot.columnconfigure(0, weight=1)
        ttk.Label(foot, text=T["footer"], style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(foot, text=T["quit"], command=self.quit).grid(row=0, column=1, rowspan=2, sticky="e", padx=(pad, 0))
        ttk.Label(foot, text=f"Version {__version__}", style="Muted.TLabel").grid(row=1, column=0, sticky="w")

        self.refresh()

    def _section(self, parent: Any, title: str) -> Any:
        frame = self.ttk.Frame(parent)
        frame.grid(sticky="ew", pady=(round(16 * self.scale), 0))
        self.ttk.Label(frame, text=title, font=self.fonts["head"]).grid(row=0, column=0, columnspan=2, sticky="w")
        return frame

    def _logo(self) -> Any:
        try:
            image = self.tk.PhotoImage(file=str(STATIC / "icons" / "icon-192.png"))
        except self.tk.TclError:  # a Tk without PNG support; the window works without a picture
            return None
        return image.subsample(max(1, round(3 / self.scale)))

    # -- keeping the window true -------------------------------------------------

    def refresh(self) -> None:
        """Bring the window in line with the server, twice a second. Widgets
        are only touched when something changed: redrawing a QR code every
        tick flickers."""
        server = self.server
        state = server.state
        now = (state, server.setup_code, server.phone_url, server.lan, server.error)
        if now != self.shown:
            self.shown = now
            self.draw(*now)
        if state == "running" and not self.opened:
            # Once, at the first start: after switching the network share
            # the browser tab is still there.
            self.opened = True
            self.browser(server.url)
        self.root.after(500, self.refresh)

    def draw(self, state: str, code: str, phone_url: str, lan: bool, error: str) -> None:
        self.dot.itemconfigure(self.dot_item, fill=DOT[state])
        self.status.configure(text=T[state])
        reachable = state in ("running", "elsewhere")
        self.open_button.configure(state="normal" if reachable else "disabled")
        self.share_box.configure(state="disabled" if state == "elsewhere" else "normal")

        text = error if state == "failed" else T["elsewhere_hint"] if state == "elsewhere" else ""
        self.message.configure(text=text)
        if text:
            self.message.grid(row=1, column=0, sticky="w", pady=(round(12 * self.scale), 0))
        else:
            self.message.grid_remove()

        self.code_text.configure(text=code)
        self.copy_button.configure(text=T["copy"])
        if code:
            self.code.grid()
        else:
            self.code.grid_remove()

        for widget in (self.qr, self.phone_url, self.phone_steps):
            widget.grid_remove()
        if not lan:
            self.phone_hint.configure(text=T["share_off"])
        elif state != "running":
            self.phone_hint.configure(text="")
        elif not phone_url:
            self.phone_hint.configure(text=T["no_network"])
        else:
            self.phone_hint.configure(text=T["share_firewall"])
            gap = round(14 * self.scale)
            drawn = self.draw_qr(phone_url)
            if drawn:
                self.qr.grid(row=3, column=0, rowspan=2, sticky="nw", pady=(gap, 0), padx=(0, gap))
            self.phone_url.configure(text=phone_url)
            self.phone_url.grid(row=3, column=1, sticky="w", pady=(gap, 0))
            self.phone_steps.configure(
                text=T["share_steps" if drawn else "share_steps_no_qr"], wraplength=self.wrap - drawn - gap
            )
            self.phone_steps.grid(row=4, column=1, sticky="nw", pady=(4, 0))

    def draw_qr(self, url: str) -> int:
        """Draw the address as a QR code; returns its width in pixels, 0
        without the library for it."""
        try:
            import segno
        except ImportError:
            return 0
        rows = [list(row) for row in segno.make(url, error="m").matrix]
        quiet = 3
        cell = max(2, round(132 * self.scale / (len(rows) + 2 * quiet)))
        side = cell * (len(rows) + 2 * quiet)
        self.qr.delete("all")
        self.qr.configure(width=side, height=side)
        for y, row in enumerate(rows):
            for x, dark in enumerate(row):
                if dark:
                    left, top = (x + quiet) * cell, (y + quiet) * cell
                    self.qr.create_rectangle(left, top, left + cell, top + cell, outline="", fill="black")
        return side

    # -- what the buttons do -----------------------------------------------------

    def open(self) -> None:
        if self.server.state in ("running", "elsewhere"):
            self.browser(self.server.url)

    def copy(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.server.setup_code)
        self.copy_button.configure(text=T["copied"])

    def show_data(self) -> None:
        show_folder(self.server.settings.data_dir)

    def toggle(self) -> None:
        lan = bool(self.share.get())
        remember(self.server.settings, lan)
        self.server.switch(lan)

    def quit(self) -> None:
        self.root.withdraw()  # stopping waits for running requests; do not sit there looking frozen
        self.server.stop()
        self.root.destroy()


def show_folder(path: Path) -> None:
    """Open a folder in the system's file manager."""
    import os
    import subprocess

    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606 - our own data folder
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])  # noqa: S603
    except OSError:
        log.warning("could not open %s", path)


def _crisp_on_windows() -> None:
    """Tell Windows this program scales itself. Otherwise the window is
    drawn small and stretched, which is blurry on every modern laptop. The
    second call gives the taskbar our icon instead of Python's."""
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("troedel.window")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass  # not Windows, or a Windows too old to care


def run(settings: Settings) -> int:
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print(T["no_tk"])  # noqa: T201
        return 2
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    # Started by double-click there is no terminal, and on Windows not even
    # an error stream: without a file, whatever goes wrong leaves no trace.
    handler = RotatingFileHandler(settings.data_dir / "troedel.log", maxBytes=500_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    server = Server(settings)
    server.lan = remembered(settings)
    # The window first: loading the app takes a moment, and a double-click
    # that shows nothing gets a second double-click.
    window = Window(server)
    server.switch(server.lan)
    window.root.mainloop()
    return 0
