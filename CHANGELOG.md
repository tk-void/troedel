# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

First public version.

### Added

- Drafting listings from photos and keywords; revising by instruction with undo.
- Local photo editing: Studio, White, Tidy, Original.
- Copy-ready fields for Kleinanzeigen, Vinted, eBay and Facebook Marketplace.
- Sales tracking and statistics.
- AI providers: Anthropic API, Gemini, OpenAI, Ollama, any OpenAI-compatible
  service, and the Claude Code CLI (experimental).
- Mandatory login: one password, first set with a one-time code from the log.
- Export of the database and original photos.
- Optional, experimental fill helper userscript, off by default.
- A demo instance with drawn items (`tools/demo.py`), used for the screenshots.
- Downloads for Windows (installer, or a ZIP to unpack) and macOS (an app in
  a disk image, Apple chip), a published container image, and a release
  workflow that builds all of them from a tag.
- `troedel window`: a small window instead of a terminal, used by the
  downloads. It shows whether Trödel runs, the address, the setup code of
  the first start, and a switch to share it in the home network with the
  address and a QR code for the phone.
- `troedel --open` opens the browser once the server is up.
- The README in German (`README.de.md`).
