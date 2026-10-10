# Contributing

Thanks for looking. A few things make contributions easy to accept.

## Setup

```bash
git clone https://github.com/tk-void/troedel.git && cd troedel
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"          # add ,cutout for the photo editing
pytest -q && ruff check .
TROEDEL_SETUP_CODE=TEST-TEST-TEST troedel --port 8199
```

The tests need no network, no API key and no model download: providers and
the cut-out model are replaced by fakes.

To look at the app with something in it, `python tools/demo.py` fills a
directory with drawn items and serves it; it prints the password. Screenshots
for the docs are taken from that instance only, never from a real one.

## Ground rules

- **English** for code, comments, commits, docs and issues. German appears
  only as interface text and as content of the German market.
- **Comments say why**, not what. If a line is there because something went
  wrong without it, say what went wrong.
- **Every change comes with a test** that fails without it.
- **Security-relevant behaviour is pinned by tests** (`tests/test_web.py`,
  `tests/test_auth.py`). Do not relax one to make a change pass; explain in
  the pull request why the rule should change.
- **The item in a photo is never altered.** `tests/test_imaging.py` holds
  that pixel by pixel.
- **Nothing is published automatically.** Trödel prepares, a person submits.
  Pull requests that log in to a marketplace, submit a form, solve captchas
  or evade bot detection will not be merged.
- **No private data in the repository**: no real addresses, names, photos of
  your home, API keys. Look over your diff for them before you push.

## Where things are

See [docs/architecture.md](docs/architecture.md).

## Marketplaces change

The fill helper and the per-platform field rules follow what the
marketplaces' forms look like today. When one changes, a fix is welcome;
please say in the pull request how you checked it against the live site.
