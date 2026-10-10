# Third-party notices

## Bundled

- **Inter** typeface, `src/troedel/web/static/fonts/inter.woff2`.
  Copyright (c) 2016 The Inter Project Authors. SIL Open Font License 1.1,
  full text in `src/troedel/web/static/fonts/LICENSE-Inter.txt`.

## Downloaded at run time (only with the `cutout` extra)

Stored under `data/models/`, not part of this repository or the package.

- **BiRefNet** (background removal), fetched by the `rembg` library on first
  use. MIT License.
- **LaMa** (retouching) as ONNX, from `huggingface.co/Carve/LaMa-ONNX`,
  pinned to a revision and verified against a SHA-256 checksum in
  `src/troedel/imaging.py`. Apache License 2.0.

## Python dependencies

Installed by pip, each under its own license: FastAPI, Uvicorn, Jinja2,
python-multipart, Pillow, pillow-heif, httpx, argon2-cffi, anthropic, and
optionally rembg with onnxruntime and segno. See each project for details.

## In the downloads for Windows and macOS

The installer, the ZIP and the disk image additionally contain a Python
runtime from the python-build-standalone project (Python Software Foundation
License, with Tcl/Tk and the other libraries listed in its `LICENSE.txt`)
and the packages above, each with its license file next to it.
