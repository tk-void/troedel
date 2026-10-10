#!/usr/bin/env python3
"""Build the downloads: something to double-click.

    python packaging/build.py windows      # dist/troedel-<version>-windows-x64.zip
                                           # on Windows with Inno Setup also ...-setup.exe
    python packaging/build.py macos        # on a Mac dist/troedel-<version>-macos-arm64.dmg,
                                           # elsewhere the same app as .tar.gz
    python packaging/build.py windows --no-cutout

Each download holds a Python of its own with Trödel and everything it needs
as ready-made wheels, and starts the small window (``troedel window``).
Nothing is compiled here, so the folders can be put together on any system:
the wheels for the target are asked for explicitly. Only the last step is
tied to its system: an installer is made on Windows, a disk image on a Mac.
Needs ``uv``.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

PYTHON = "3.12"

# python.org has no unpack-and-run Python with Tk in it, for either system;
# these builds are made for exactly that. Both come from the same release.
# Apple Silicon only: the cut-out's runtime is no longer published for Intel
# Macs.
PYTHON_RELEASE = "20261009"
PYTHON_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/"
    f"{PYTHON_RELEASE}/cpython-3.12.15%2B{PYTHON_RELEASE}-{{target}}-install_only_stripped.tar.gz"
)
WINDOWS = ("x86_64-pc-windows-msvc", "11ed9f8a6ac64fb1b5a55e40e305a6744a3f77a70863c8f8197a6e4349abc64a")
MACOS = ("aarch64-apple-darwin", "233f8e15255b3e1d1fd47ea5dd5230dfed803f371138e896e54d98c60ae19f6f")

BUNDLE_ID = "io.github.tk-void.troedel"


def version() -> str:
    scope: dict[str, str] = {}
    exec((ROOT / "src/troedel/__init__.py").read_text(encoding="utf-8"), scope)  # noqa: S102 - our own file
    return scope["__version__"]


def run(*args: str | Path) -> None:
    subprocess.run([str(a) for a in args], check=True)  # noqa: S603


def download(url: str, sha256: str) -> bytes:
    with urllib.request.urlopen(url, timeout=300) as response:  # noqa: S310 - fixed https address
        data = response.read()
    found = hashlib.sha256(data).hexdigest()
    if found != sha256:
        raise SystemExit(f"{url}: checksum {found}, expected {sha256}")
    return data


def python(folder: Path, target: tuple[str, str], site: str, extras: str, work: Path) -> None:
    """Unpack the Python for ``target`` into ``folder/python`` and install
    Trödel into it."""
    platform, sha256 = target
    with tarfile.open(fileobj=io.BytesIO(download(PYTHON_URL.format(target=platform), sha256))) as t:
        t.extractall(folder, filter="tar")  # unpacks to python/
    packages = folder / "python" / site
    if not packages.is_dir():
        raise SystemExit("the Python archive has an unexpected layout")
    wheels = work / "wheel"
    run("uv", "build", "--wheel", "--out-dir", wheels, ROOT)
    (wheel,) = wheels.glob("troedel-*.whl")
    # uv rather than pip: asked for another platform, pip still decides by
    # the machine it runs on which optional dependencies apply, and then
    # looks for a Windows build of a Linux-only package.
    run(
        "uv", "pip", "install", "--target", packages, "--no-compile",
        "--python-platform", platform, "--python-version", PYTHON,
        # Wheels only: a source package would be built for the machine this
        # runs on, not for the target.
        "--only-binary", ":all:",
        f"troedel{extras} @ {wheel.as_uri()}",
    )  # fmt: skip
    # Start scripts for the build machine's layout; nothing uses them.
    for scripts in ("bin", "Scripts"):
        shutil.rmtree(packages / scripts, ignore_errors=True)
    # Compiled ahead, Trödel starts in a blink instead of seconds, also from
    # a place it cannot write to (a disk image, a signed app). "unchecked":
    # archives do not keep the file times the usual check relies on. Run by
    # a Python of the bundled version, whatever runs this script: only that
    # one writes files the bundled one can read.
    subprocess.run(  # noqa: S603
        ["uv", "run", "--no-project", "--python", PYTHON, "python", "-m", "compileall", "-q",
         "--invalidation-mode", "unchecked-hash", str(packages)],
        check=False,  # packages carry the odd file that is not meant to compile
        stdout=subprocess.DEVNULL,
    )  # fmt: skip
    if not any(packages.glob(f"troedel/__pycache__/*.cpython-{PYTHON.replace('.', '')}.pyc")):
        raise SystemExit("precompiling the packages left nothing behind")


def as_text(source: Path, target: Path, newline: str) -> None:
    text = source.read_text(encoding="utf-8").replace("\r\n", "\n")
    target.write_bytes(text.replace("\n", newline).encode("utf-8"))


def notices(folder: Path, newline: str) -> None:
    as_text(ROOT / "LICENSE", folder / "LICENSE.txt", newline)
    as_text(ROOT / "THIRD_PARTY_NOTICES.md", folder / "THIRD_PARTY_NOTICES.txt", newline)


def windows(folder: Path, extras: str, work: Path, out: Path) -> list[Path]:
    python(folder, WINDOWS, "Lib/site-packages", extras, work)
    for file in ("Troedel.bat", "LIESMICH.txt"):
        as_text(HERE / "windows" / file, folder / file, "\r\n")
    shutil.copy(HERE / "windows" / "troedel.ico", folder / "troedel.ico")
    notices(folder, "\r\n")

    archive = out / f"{folder.name}.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                z.write(path, Path(folder.name) / path.relative_to(folder))
    made = [archive]

    compiler = inno_setup()
    if compiler:
        # With a byte order mark, or the compiler reads the "ö" as two
        # characters of the Windows code page.
        script = work / "troedel.iss"
        script.write_text((HERE / "windows" / "troedel.iss").read_text(encoding="utf-8"), encoding="utf-8-sig")
        setup = f"{folder.name}-setup"
        run(
            compiler, "/Qp", f"/DVersion={version()}", f"/DSource={folder}", f"/DOut={out.resolve()}",
            f"/DName={setup}", script,
        )  # fmt: skip
        made.append(out / f"{setup}.exe")
    else:
        print("note: no installer, that needs Windows with Inno Setup (iscc)")
    return made


def inno_setup() -> str | None:
    if sys.platform != "win32":
        return None
    import os

    found = shutil.which("iscc")
    usual = Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe"
    return found or (str(usual) if usual.is_file() else None)


def macos(folder: Path, extras: str, work: Path, out: Path) -> list[Path]:
    import plistlib

    app = folder / "Troedel.app"
    contents = app / "Contents"
    resources = contents / "Resources"
    (contents / "MacOS").mkdir(parents=True)
    resources.mkdir()
    python(resources, MACOS, f"lib/python{PYTHON}/site-packages", extras, work)
    start = contents / "MacOS" / "Troedel"
    as_text(HERE / "macos" / "Troedel", start, "\n")
    start.chmod(0o755)
    shutil.copy(HERE / "macos" / "troedel.icns", resources / "troedel.icns")
    notices(resources, "\n")
    with (contents / "Info.plist").open("wb") as f:
        plistlib.dump(
            {
                "CFBundleName": "Trödel",
                "CFBundleDisplayName": "Trödel",
                "CFBundleIdentifier": BUNDLE_ID,
                "CFBundleExecutable": "Troedel",
                "CFBundleIconFile": "troedel",
                "CFBundlePackageType": "APPL",
                "CFBundleShortVersionString": version(),
                "CFBundleVersion": version(),
                "CFBundleDevelopmentRegion": "de",
                "LSMinimumSystemVersion": "11.0",
                "LSArchitecturePriority": ["arm64"],
                "LSApplicationCategoryType": "public.app-category.productivity",
                "NSHighResolutionCapable": True,
            },
            f,
        )
    as_text(HERE / "macos" / "LIESMICH.txt", folder / "LIESMICH.txt", "\n")

    if sys.platform == "darwin":
        # Not a signature that says who made this, only a seal: without one
        # macOS calls a downloaded app "damaged" instead of "unverified",
        # and for "damaged" there is no "open anyway".
        run("codesign", "--force", "--deep", "--sign", "-", app)
        (folder / "Applications").symlink_to("/Applications")
        image = out / f"{folder.name}.dmg"
        image.unlink(missing_ok=True)
        # "Resource busy" is hdiutil's answer when something else looks at
        # the volume it is filling, usually Spotlight or the malware scan,
        # and more likely the bigger the folder. It passes; try again.
        for attempt in range(1, 7):
            done = subprocess.run(  # noqa: S603
                ["hdiutil", "create", "-volname", "Troedel", "-srcfolder", str(folder), "-format", "UDZO", "-ov",
                 str(image)],
                check=False,
            )  # fmt: skip
            if done.returncode == 0:
                break
            print(f"hdiutil failed (attempt {attempt} of 6), waiting")
            time.sleep(5 * attempt)
        else:
            raise SystemExit("hdiutil could not create the disk image")
        return [image]
    # tar keeps what a zip written here would lose: the links inside the
    # Python and which files may be run.
    print("note: no disk image and no seal, those need a Mac; packing the app as it is")
    archive = out / f"{folder.name}.tar.gz"
    archive.unlink(missing_ok=True)
    with tarfile.open(archive, "w:gz") as t:
        t.add(folder, arcname=folder.name)
    return [archive]


def build(target: str, out: Path, cutout: bool) -> list[Path]:
    name = f"troedel-{version()}-{'windows-x64' if target == 'windows' else 'macos-arm64'}"
    out.mkdir(parents=True, exist_ok=True)
    extras = "[cutout,desktop]" if cutout else "[desktop]"
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        folder = work / name
        folder.mkdir()
        return (windows if target == "windows" else macos)(folder, extras, work, out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", choices=["windows", "macos"])
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    parser.add_argument("--no-cutout", action="store_true", help="leave out the local photo editing (much smaller)")
    args = parser.parse_args()
    for made in build(args.target, args.out, not args.no_cutout):
        print(f"{made}  {made.stat().st_size / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
