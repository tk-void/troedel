"""The window of the downloads. The server half is tested for real; the Tk
half only where there is a screen to draw on."""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.request
from dataclasses import replace

import pytest

from troedel import cli, desktop


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(server: desktop.Server, state: str) -> None:
    for _ in range(100):
        if server.state == state:
            return
        time.sleep(0.1)
    raise AssertionError(f"still {server.state}, expected {state}: {server.error}")


@pytest.fixture
def server(settings):
    server = desktop.Server(replace(settings, port=free_port()))
    yield server
    server.stop()


class TestServer:
    def test_runs_for_this_computer_only_and_stops(self, server):
        server.start(lan=False)
        wait_for(server, "running")
        with urllib.request.urlopen(f"http://127.0.0.1:{server.settings.port}/health", timeout=5) as r:
            assert json.loads(r.read()) == {"status": "ok"}
        assert server._uvicorn.config.host == "127.0.0.1"
        assert server.phone_url == ""
        server.stop()
        assert not desktop._taken("127.0.0.1", server.settings.port)

    def test_shows_the_setup_code_until_a_password_exists(self, server):
        server.start(lan=False)
        wait_for(server, "running")
        code = server.setup_code
        assert len(code.replace("-", "")) == 12
        server._app.state.ctx.auth.setup(code, "correct horse battery staple")
        assert server.setup_code == ""

    def test_shared_gives_the_address_for_the_phone(self, server, monkeypatch):
        monkeypatch.setattr(desktop, "lan_address", lambda: "192.0.2.7")
        server.start(lan=True)
        wait_for(server, "running")
        assert server._uvicorn.config.host == "0.0.0.0"  # noqa: S104
        assert server.phone_url == f"http://192.0.2.7:{server.settings.port}"
        monkeypatch.setattr(desktop, "lan_address", lambda: "")
        assert server.phone_url == ""

    def test_switching_restarts_on_the_other_address(self, server):
        server.start(lan=False)
        wait_for(server, "running")
        first = server._uvicorn
        server.switch(True)
        for _ in range(100):
            if server._uvicorn is not None and server._uvicorn is not first and server.state == "running":
                break
            time.sleep(0.1)
        assert server.lan and server._uvicorn.config.host == "0.0.0.0"  # noqa: S104

    def test_a_port_someone_else_holds_is_an_error_not_a_hang(self, server):
        with socket.socket() as other:
            other.bind(("127.0.0.1", server.settings.port))
            other.listen()
            server.start(lan=False)
            assert server.state == "failed"
            assert str(server.settings.port) in server.error

    def test_a_second_start_notices_the_first(self, server, settings):
        server.start(lan=False)
        wait_for(server, "running")
        second = desktop.Server(replace(settings, port=server.settings.port))
        second.start(lan=False)
        assert second.state == "elsewhere"
        assert second.setup_code == ""

    def test_a_broken_start_is_reported(self, settings):
        def broken(_settings):
            raise RuntimeError("no")

        server = desktop.Server(replace(settings, port=free_port()), make_app=broken)
        server.start(lan=False)
        assert server.state == "failed"
        assert "troedel.log" in server.error


class TestRemembering:
    def test_the_switch_survives_a_restart(self, settings):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        assert desktop.remembered(settings) is False
        desktop.remember(settings, True)
        assert desktop.remembered(settings) is True

    def test_without_a_choice_the_configured_address_decides(self, settings):
        assert desktop.remembered(replace(settings, host="0.0.0.0")) is True  # noqa: S104

    def test_a_damaged_file_is_ignored(self, settings):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        (settings.data_dir / "window.json").write_text("{", encoding="utf-8")
        assert desktop.remembered(settings) is False


class TestCommand:
    def test_window_keeps_its_data_in_the_home_folder(self, monkeypatch, tmp_path):
        seen = []
        monkeypatch.setattr(desktop, "run", lambda settings: seen.append(settings) or 0)
        monkeypatch.setattr(desktop, "default_data_dir", lambda: tmp_path / "Troedel")
        monkeypatch.delenv("TROEDEL_DATA_DIR", raising=False)
        assert cli.main(["window"]) == 0
        assert seen[0].data_dir == tmp_path / "Troedel"

    def test_an_explicit_folder_wins(self, monkeypatch, tmp_path):
        seen = []
        monkeypatch.setattr(desktop, "run", lambda settings: seen.append(settings) or 0)
        monkeypatch.setenv("TROEDEL_DATA_DIR", str(tmp_path / "env"))
        cli.main(["window"])
        cli.main(["window", "--data-dir", str(tmp_path / "arg")])
        assert [s.data_dir for s in seen] == [tmp_path / "env", tmp_path / "arg"]


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="needs a screen")
class TestWindow:
    def test_shows_what_the_server_says_and_opens_the_browser_once(self, server, monkeypatch):
        pytest.importorskip("tkinter")
        monkeypatch.setattr(desktop, "lan_address", lambda: "192.0.2.7")
        server.start(lan=True)
        wait_for(server, "running")
        urls = []
        window = desktop.Window(server, browser=urls.append)
        try:
            window.root.update()
            assert window.status.cget("text") == desktop.T["running"]
            assert window.code_text.cget("text") == server.setup_code
            assert window.phone_url.cget("text") == "http://192.0.2.7:" + str(server.settings.port)
            window.refresh()
            window.open()
            assert urls == [server.url, server.url]  # once by itself, once by the button
        finally:
            window.root.destroy()


def test_showing_the_folder_survives_a_missing_file_manager(monkeypatch, tmp_path):
    import subprocess

    def gone(*a, **k):
        raise FileNotFoundError("xdg-open")

    monkeypatch.setattr(subprocess, "Popen", gone)
    monkeypatch.setattr(desktop.sys, "platform", "linux")
    desktop.show_folder(tmp_path)


def test_starts_without_a_console(settings, monkeypatch):
    """Started by double-click on Windows there is no console at all: the
    output streams are None, and whatever asks them a question crashes."""
    monkeypatch.setattr(desktop.sys, "stdout", None)
    monkeypatch.setattr(desktop.sys, "stderr", None)
    server = desktop.Server(replace(settings, port=free_port()))
    try:
        server.start(lan=False)
        wait_for(server, "running")
    finally:
        server.stop()
