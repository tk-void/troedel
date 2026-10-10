"""Command line: start the server, or recover access.

troedel                   start the web app
troedel --open            ... and open it in the browser
troedel window            ... with a small window instead of a terminal
troedel reset-password    forget the password and print a new setup code
troedel version
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from . import __version__, config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="troedel", description="Photo in, classified ad out.")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "window", "reset-password", "version"])
    parser.add_argument("--host", help="address to listen on (default: TROEDEL_HOST or 127.0.0.1)")
    parser.add_argument("--port", type=int, help="port (default: TROEDEL_PORT or 8099)")
    parser.add_argument("--data-dir", help="where the database and photos live (default: TROEDEL_DATA_DIR or ./data)")
    parser.add_argument("--open", action="store_true", help="open the app in the browser once it is up")
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    try:
        settings = config.load()
    except config.ConfigError as exc:
        print(f"troedel: {exc}", file=sys.stderr)
        return 2
    overrides = {k: v for k, v in (("host", args.host), ("port", args.port)) if v}
    if args.data_dir:
        from pathlib import Path

        overrides["data_dir"] = Path(args.data_dir).expanduser()
    elif args.command == "window" and not os.environ.get(config.PREFIX + "DATA_DIR"):
        # Double-clicked, the current directory is wherever the system
        # felt like; "./data" would be a different place every time.
        from .desktop import default_data_dir

        overrides["data_dir"] = default_data_dir()
    if overrides:
        from dataclasses import replace

        settings = replace(settings, **overrides)

    if args.command == "reset-password":
        # Whoever can run this can read the data directory anyway; it is the
        # way back in for someone who forgot the password.
        from .auth import Auth
        from .db import DB

        code = Auth(DB(settings.db_path)).reset()
        print(
            "Password and all sessions removed. Restart Trödel if it is running,\n"
            f"open it in a browser and enter this code:\n\n    {code}\n"
        )
        print("Note: a running server prints its own code at start; use that one after the restart.")
        return 0

    if args.command == "window":
        from .desktop import run

        return run(settings)

    import uvicorn

    from .web.app import create_app

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if settings.host not in ("127.0.0.1", "localhost", "::1"):
        logging.getLogger("troedel").warning(
            "Listening on %s: reachable from the network. Use HTTPS if that network is not your own; "
            "see docs/security.md.",
            settings.host,
        )
    app = create_app(settings)
    if args.open:
        _open_when_up(settings.port, lan=settings.host not in ("127.0.0.1", "localhost", "::1"))
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="warning",
        proxy_headers=False,
        server_header=False,
    )
    return 0


def lan_address() -> str:
    """This computer's address in the local network, or "" if it has none.
    Connecting a UDP socket sends nothing; it only makes the system pick the
    interface it would use."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            return s.getsockname()[0]
    except OSError:
        return ""


def _open_when_up(port: int, lan: bool = False, tries: int = 100) -> None:
    """Open the browser as soon as the server answers, from a thread: the
    server itself blocks until it is stopped. Opening at once would show
    "cannot connect", which looks like a broken install.

    Started like this, Trödel runs on someone's desktop, not in a container,
    so the address of this machine is the one a phone has to open, and worth
    printing."""
    import threading
    import time
    import urllib.request
    import webbrowser

    def wait() -> None:
        for _ in range(tries):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):  # noqa: S310
                    break
            except OSError:
                time.sleep(0.3)
        else:
            return
        address = lan_address() if lan else ""
        if address:
            print(f"  On your phone, in the same network:  http://{address}:{port}\n", flush=True)  # noqa: T201
        webbrowser.open(f"http://localhost:{port}")

    threading.Thread(target=wait, name="open-browser", daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())
