# Architecture

A small FastAPI app with server-rendered pages, a SQLite database, and two
background threads. No build step, no JavaScript framework.

```
src/troedel/
  cli.py            the `troedel` command
  desktop.py        `troedel window`: the small window of the downloads
  config.py         settings from the environment, fixed while running
  db.py             SQLite: schema, migrations, every query
  auth.py           password, sessions, login throttle, helper tokens
  secrets_store.py  the API key file
  listing.py        the shape of a listing; compose, revise, find distractors
  imaging.py        read photos, cut out, studio/white/tidy looks
  worker.py         background threads: one for texts, one for photos
  stats.py          takings and sales
  markets/          a country: language of listings, prompts, platforms
    de.py
  providers/        adapters to language models
    base.py           the interface, schema checking
    anthropic_api.py  openai_compat.py  claude_cli.py
  web/
    app.py          routes: pages and the JSON API they call
    security.py     login gate, origin check, response headers
    text.py         German interface text produced in Python
    templates/      Jinja2
    static/         troedel.css, troedel.js, theme.js, troedel.user.js
tools/demo.py       a demo instance with drawn items, for screenshots
packaging/          the downloads built for a release (docs/releasing.md)
```

## How a listing comes to be

1. `POST /api/items` stores the photos (decoded, re-encoded, metadata
   dropped) and an item in state `queued`, then queues two kinds of work.
2. The **text thread** sends up to four photos and the keywords to the
   provider and saves the answer as `data` (what you edit) and `suggestion`
   (kept, so the suggested price stays visible). State becomes `draft`.
3. The **photo thread** produces the chosen look for each photo. The mask is
   computed once and reused for other looks.
4. The page polls `/api/items/{id}` while either is running.

State lives in the database, not in the queues: after a restart,
`Worker.resume` picks up what was open.

Item states: `queued → writing → draft ⇄ online → sold`, plus `revising`,
`failed`, `archived`. Photo states: `pending`, `done`, `failed`, `off`.

## Decisions worth knowing

- **Listing fields are JSON in one column.** They come from a model and are
  edited by hand; nothing queries by them. A column per field would need a
  migration for every new field.
- **Schema changes are append-only migrations** in `db.MIGRATIONS`, tracked
  with `PRAGMA user_version`. Never edit an existing one.
- **Access control is in one place.** Routes do not check for a login;
  `web/security.py` does, for all of them. A new route is protected by
  default, and `tests/test_web.py` walks every route to prove it.
- **The provider is looked up per job**, so changing it in the settings
  needs no restart.
- **Photo editing is optional** (`cutout` extra) because it pulls in
  onnxruntime and model downloads. Without it, photos stay as taken.
- **The object in a photo is never altered.** Cut-outs composite original
  pixels through a mask. Generative retouching (LaMa) happens only in the
  *Tidy* look, only inside boxes marked as clutter, and the object is laid
  over the result again from the original.

## Languages and markets

Two things that are easy to confuse:

- The **market** (`markets/de.py`) is the country: the language listings are
  written in, the prompts, the currency, the platforms with their limits and
  vocabulary. A second country is a second module with the same names.
- The **interface language** is German only. Its text lives in the
  templates, in the `STRINGS` table at the top of `static/troedel.js`, in
  `T` in the userscript, and in `web/text.py`. A second interface language
  means moving those into catalogues and choosing one per request. The text
  is already separated from logic and identifiers to keep that step small,
  but it has not been taken.

Identifiers, stored values (`very_good`, `parcel_s`, `draft`) and API paths
are English throughout, so neither step touches the database.
