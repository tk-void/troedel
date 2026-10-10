# The fill helper

An optional userscript that fills the "new listing" form on Kleinanzeigen
and Vinted with what Trödel prepared: photos, title, description, price.

**It is experimental and off by default.**

## Before you switch it on

- **It may be against a marketplace's terms of use.** Marketplaces commonly
  forbid automated mechanisms without their consent, and they can warn,
  suspend or permanently exclude accounts. How a helper that fills fields in
  your own browser is judged is not something this project can tell you.
  **The risk is yours.**
- It **never submits** a listing, never logs in, never touches captchas or
  bot checks, and does nothing until you press its button. You choose
  category and condition, look everything over and press the marketplace's
  own button. This keeps you in control; it is not a guarantee of anything.
- **It breaks.** It depends on how the marketplaces' forms are built today.
  When they change, fields stop being filled until someone updates the
  script. Every field stays available to copy, in Trödel and in the
  helper's panel.
- The authors accept no liability for suspended accounts or any other
  consequence. See the license.

## How it works

The script runs in a userscript manager in your browser (Userscripts for
Safari, Violentmonkey for Firefox, Tampermonkey for Chrome). On the
marketplace's "new listing" page it shows a small Trödel button. Pressed, it
fetches the listing from your Trödel instance and sets the form fields.

Each installation gets its own access token, created when you press
*Skript für dieses Gerät erzeugen*:

- The token is written into that one copy of the script. Trödel stores only
  its hash.
- It can list open items, read one item's fields and photos, and mark an
  item as listed. It cannot change or delete listings, read settings, or
  reach anything else.
- The install link works for a few minutes, then it is dead.
- Switching the helper off in Trödel revokes every token at once.
- Requests are made by the userscript manager, not by the marketplace's
  page, so the page never sees the token.

There is no automatic update. After updating Trödel, create the script again
if the helper stopped working.

## Not for other marketplaces' forms

eBay and Facebook Marketplace are copy-only. Pull requests that add
submitting, logging in, or evading detection will not be merged.
