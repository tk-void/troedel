# AI providers

Trödel needs one thing from a language model: look at a few photos, read a
few words, and return a JSON object that fits a schema. Every provider is an
adapter to that (`src/troedel/providers/`).

Choose one in **Settings → KI-Anbieter**, then press *Testen*: it sends one
tiny request, so a wrong key shows up there and not on your first listing.

## What is sent

Per item: up to four photos (`TROEDEL_ANALYSIS_PHOTOS`), downscaled to 1568
pixels on the long edge, re-encoded without metadata, plus your keywords and
the instruction. For the *Tidy* look, the photos are sent once more to ask
where the clutter is. Nothing else leaves your machine, and nothing at all
with a local provider.

## Claude (Anthropic API)

An API key from the Anthropic Console, billed per use. Uses structured
outputs, so answers always parse. Default model `claude-opus-5-5`;
`claude-sonnet-5-5` and `claude-haiku-4-5` cost less. A listing is a few
thousand tokens in and a few hundred out.

Some photos (a kitchen knife, a toy gun) can trip a safety classifier. For
models that support it, Trödel asks the API to retry such a request on the
model Anthropic recommends instead of failing.

## Gemini

An API key from Google AI Studio, used through Google's OpenAI-compatible
endpoint. Default model `gemini-3.6-flash`: on the free tier it has proven more
reliably available than the newest Flash model, whose free quota can be zero
for an account. Your own limits per model are shown at
`aistudio.google.com/rate-limit`.

There is a free tier. **On the free tier Google states that your content may
be used to improve its products.** For photos of things on your living-room
floor you may or may not mind; decide knowingly.

## OpenAI

An API key and the name of a model that accepts images. No default model is
preset: enter the one you want.

## Ollama and other local servers

Photos stay on your machine. You need a vision-capable model pulled in
Ollama and its name in the settings; the address defaults to
`http://127.0.0.1:11434/v1`. In Docker, `127.0.0.1` is the container itself:
use the host's address instead.

Small local models follow the schema less reliably and judge prices worse.
Trödel checks every answer and asks once more with the complaint attached
before giving up.

## Any OpenAI-compatible service

*Anderer Dienst*: an address, a model, a key if the service wants one.
OpenRouter and LM Studio work this way.

## Claude Code CLI (experimental)

Uses the `claude` program that is installed and signed in on the same
machine, so it only makes sense when Trödel runs directly on your computer,
not in a container.

Read this before using it:

- Trödel starts the unmodified program once per request and never sees,
  stores or forwards a credential. Whatever account the program is signed in
  with is used and billed.
- Anthropic's guidance for software that builds on Claude is to use an API
  key. **Whether your plan's terms cover calling the CLI from another program
  like this is for you to check with Anthropic.** This project makes no claim
  that they do.
- Claude Code's documentation says that `--bare`, a mode that does not use
  a subscription sign-in, will become the default for non-interactive runs.
  When that happens this provider needs an API key too and has no advantage
  over the Anthropic one. It may be removed from Trödel without notice.

The model gets no tools: no shell, no file access, no network, no settings
or hooks from disk. `tests/test_providers.py` pins those switches.

## Adding a provider

Implement `ask(prompt, *, system, schema, images, model) -> Answer` (see
`providers/base.py`), raise `ProviderUnavailable` for anything worth
retrying later and `ProviderError` with a `code` otherwise, register it in
`providers/__init__.py`, and add its name and note to `web/text.py`. Tests
go in `tests/test_providers.py`, against a fake transport: no test may need
a network or a key.
