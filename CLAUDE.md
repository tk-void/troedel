# Working on Trödel

Photo in, classified ad out. Overview: `README.md`. Structure and the
reasons behind it: `docs/architecture.md`.

## This repository is public

Everything committed here is published, including every commit in the
history. Treat that as irreversible.

1. **Nothing private goes in.** No real network addresses, host names,
   people's names, home directories, paths from someone's server, API keys,
   tokens, mail addresses, photos of anyone's home, or text copied from a
   private project without reading it first. Examples use `example.org`,
   `192.0.2.x`, `Musterstadt`, and generated images.
2. **Only the maintainer publishes.** The key for the public remote is
   locked with a passphrase that only the maintainer knows and that is asked
   for on every push. An agent may prepare a push when asked, and then hands
   over: the maintainer reads what the push hook says will go out and types
   the passphrase. Never ask for the passphrase, never load the key into an
   SSH agent, never look for another way to the public remote. The same goes
   for tags: a tag `v*` on the public remote publishes a release
   (`docs/releasing.md`).
3. **Before every commit, run the maintainer's leak guard** and fix what it
   reports. It is not part of this repository; it lives next to it:

   ```bash
   python3 ../leakguard/leakcheck.py --tree
   ```

   If it is not there, or reports that it cannot run, stop and say so. The
   same guard runs as a pre-push hook over every commit about to be
   published and refuses the push on any finding.
4. **Never bypass the guard**: no `--no-verify`, no rewording a finding until
   it slips through, no moving it into a file the guard skips. If a rule is
   wrong, tell the maintainer.
5. **Commit metadata is published too.** Author and committer must be the
   maintainer's public identity (a `noreply` address), never a private
   mail address. No links to private sessions or tickets in messages, and
   no `Co-Authored-By` line for an AI assistant or any other tool: the
   maintainer is the only author on record.
6. **Screenshots and sample data come from a demo instance** with made-up
   items, never from a real one. Images carry no EXIF data.

## Language and style

- English for code, comments, commit messages and docs. German only as
  interface text and as content of the German market (`markets/de.py`,
  templates, `web/text.py`, the `STRINGS`/`T` tables in the scripts and in
  `desktop.py`, the read-me files of the downloads). `README.de.md` is the
  German translation of `README.md`: change both together, the English one
  leads.
- Comments say **why**. If a line exists because something broke without
  it, say what broke.
- Match the surrounding code. No new dependency without a reason that
  outweighs its weight; say the reason in the commit.

## Lines that are not moved without the maintainer

1. **Nothing is published automatically.** No logging in to a marketplace,
   no submitting, no captcha or bot-detection workarounds. The fill helper
   fills fields and stops.
2. **The item in a photo is never altered.** Cut-out is mask plus
   compositing of original pixels. Generative retouching only in the "tidy"
   look, only inside marked boxes, never on the object. `tests/test_imaging.py`
   pins this.
3. **Nothing is served without a login**, except what `web/security.py`
   lists as public. A new public path needs a reason in the code and in
   `docs/security.md`; `tests/test_web.py` names every open route.
4. **Secrets never reach a browser, a log, the database or an export.**
5. **The model gets no tools.** `tests/test_providers.py` pins the switches
   of the CLI provider.
6. **Security tests are not relaxed to make a change pass.**

## Checks

```bash
pip install -e ".[dev]"
pytest -q            # no network, no key, no model download needed
ruff check .
python3 ../leakguard/leakcheck.py --tree   # maintainer's machine only
```

## Good to know

- Request bodies (`BaseModel` classes) in `web/app.py` live at module level:
  with postponed annotations FastAPI cannot resolve classes defined inside
  `create_app`, and answers 422 to every body.
- The stylesheet, the templates and `troedel.js` share class names and data
  attributes; `tests/test_frontend.py` fails when they drift apart.
- Inline scripts need `nonce="{{ nonce }}"`, and there are no inline event
  handlers: the content security policy blocks both silently.
- A schema change is a new entry in `db.MIGRATIONS`, never an edit.
- The fill helper's selectors mirror the marketplaces' forms and age. A fix
  should say how it was checked against the live site.
