# Releasing

A release is a tag. Pushing `v<version>` starts `.github/workflows/release.yml`,
which runs the checks again and then publishes, on the releases page:

- `troedel-<version>-windows-x64-setup.exe`: an installer (Inno Setup) for
  the current user, with a start menu entry. It installs a Python of its own
  with Trödel and its dependencies in it.
- `troedel-<version>-windows-x64.zip`: the same folder without the installer,
  started by `Troedel.bat`. Both are built by `packaging/build.py windows`
  and started once by `packaging/windows/smoke.ps1`.
- `troedel-<version>-macos-arm64.dmg`: `Troedel.app` for Macs with an Apple
  chip, built the same way. Built by `packaging/build.py macos`, started once
  by `packaging/macos/smoke.sh`.
- the Python packages (wheel and source archive), for `pipx install <file>`.
- the container image `ghcr.io/<owner>/troedel:<version>` and `:latest`, for
  amd64 and arm64.

The release is created as a draft first. Each build job uploads its own
files into it, and the last job makes it public once every file is there. A
failed run leaves a draft behind that nobody else sees; running the failed
jobs again continues with it.

## Steps

1. Set the version in `pyproject.toml` and `src/troedel/__init__.py`. The
   workflow refuses a tag that differs from it.
2. In `CHANGELOG.md`, rename *Unreleased* to the version with today's date and
   start a new *Unreleased*.
3. Commit, and make sure CI is green on that commit, including the `windows`
   and `macos` jobs: they build and start the same archives the release will
   publish.
4. Tag and push, as the maintainer:

   ```bash
   git tag v0.2.0 && git push origin main v0.2.0
   ```

5. The first time only: on GitHub, open the package `troedel` under
   *Packages* and set its visibility to public. A new package starts private,
   and nobody else could pull the image.
6. Try both downloads on real machines now and then, fetched with a browser
   from the releases page. The smoke tests run on build servers that have
   more installed than a fresh PC, and on files that were never downloaded:
   what Windows SmartScreen and macOS Gatekeeper do to a download only shows
   there.

## What a release does not have

- **A signature.** The downloads are unsigned. Windows SmartScreen warns on
  first start; macOS refuses the app until it is allowed in the system
  settings. The app carries an ad-hoc seal only (`codesign --sign -`), which
  says nothing about who made it but keeps macOS from calling it damaged.
  Signing would remove both warnings and costs money every year (a
  code-signing certificate, an Apple developer account).
- **Intel Macs.** The runtime the cut-out needs is no longer published for
  them.
- **PyPI.** Nothing is uploaded there yet; the wheel is attached to the
  release instead.

## Where each piece can be built

`packaging/build.py` puts both folders together on any system, because it
only unpacks a ready-made Python and ready-made wheels. The last step is
tied to its system: the installer is compiled on Windows (it needs Inno
Setup, `iscc`), the disk image and the seal are made on a Mac. Elsewhere the
script says so and leaves a ZIP or a `.tar.gz` of the app, good for looking
inside and not for publishing.

All downloads start the same thing, `python -I -m troedel window`: the small
window in `src/troedel/desktop.py`. To see it without building anything:
`pip install -e ".[desktop]"` and `troedel window`.

## Moving the bundled Python

`packaging/build.py` pins both Pythons by address and SHA-256, from one
python-build-standalone release (python.org's own downloads come without Tk
or need installing). To move on, change the release and both checksums
together and keep them on the same minor version as `PYTHON`; the checksums
are in the release's `SHA256SUMS`.
