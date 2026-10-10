# Security

Trödel holds photos from someone's home and, optionally, an API key that
costs money when used. This page says what protects them, and where the
protection ends.

## The model

One person or household, one password, a network they control. Trödel is
**not built to be exposed to the internet**, and nothing here should be read
as saying it is safe to do so.

## What is in place

**Nothing without a login.** Every request passes one check before it
reaches a route (`web/security.py`). Only the login page, the first-run
setup, `/health` (which answers `{"status": "ok"}` and nothing else), the
web app manifest and static files are served without a session. A test
walks every route and fails if one answers without a login.

**First-run setup needs a code from the log.** A fresh instance has no
password. To keep the first visitor from claiming it, setting the password
requires a one-time code that the server prints at start. Whoever can read
the server's output is whoever runs it.

**Passwords** are hashed with Argon2id, at least 10 characters long, and
never logged. Changing the password signs out every other device.

**Sessions** are random 256-bit tokens. The browser holds the token in an
`HttpOnly`, `SameSite=Lax` cookie (also `Secure` over HTTPS); the database
holds only its SHA-256, so a leaked copy of the database lets nobody in.
Sessions end after 30 days without use and after 180 days in any case.

**Guessing is throttled.** Five free attempts per client, then the wait
doubles up to 15 minutes; many failures from many addresses pause all logins
briefly. The same applies to the setup code.

**Other websites cannot act for you.** Every request that changes something
must carry an `Origin` (or `Referer`) matching Trödel's own address. A
session cookie alone is not enough.

**The page defends itself.** A strict content security policy (scripts only
from Trödel itself, inline scripts only with a per-response nonce, no
framing), `nosniff`, and no caching of pages and API answers.

**Uploads are treated as hostile.** Size and count are limited, every upload
is decoded and re-encoded as a JPEG under a random name, metadata is
dropped, and the photo route serves nothing but names of that exact shape.

**The API key stays put.** Typed into the settings, it is written to
`data/secrets.json` with mode `600`, apart from the database. No page or
API response contains it; the settings show its last four characters. It is
not part of an export. Changing the provider discards it, so it is never
sent to a service it was not issued by.

**The model cannot act.** Providers return text. The experimental Claude
Code provider starts the CLI with every tool disabled, so text hidden in a
photo has nothing to act with.

**The fill helper has its own, narrow token**, one per installation: it can
read listings and photos and mark an item as listed. Switching the helper
off revokes all of them.

## Where it ends

**No encryption on its own.** Trödel speaks HTTP. On `localhost` that does
not matter. On a network, everyone on the path can read the traffic,
including the password when you log in. The login page says so when it
applies. In a home network you trust, that is a common and reasonable
trade-off; on any other network, use HTTPS.

The window of the downloads (`troedel window`) listens on this computer only
until *Im Heimnetz freigeben* is ticked, and says there that the switch is
for one's own network. The setup code it shows never leaves the window: it
is read from the running app, not written to the log file next to the data.

**Whoever can read the data directory can read everything**, including the
API key. Protect the directory like the photos in it.

**One password, no roles.** Everyone who knows it can do everything.

**The command line can reset the password** (`troedel reset-password`). That
is the recovery path, and it means access to the machine is access to Trödel.

## HTTPS with Caddy

Caddy obtains and renews certificates by itself. With a name that points to
your server (`troedel.example.org`):

```yaml
# compose.yaml
services:
  troedel:
    build: .
    restart: unless-stopped
    environment:
      TROEDEL_TRUST_PROXY: "true"     # only because Caddy sits in front
    volumes:
      - ./data:/data
    # no "ports": only Caddy can reach it
  caddy:
    image: caddy:2
    restart: unless-stopped
    ports: ["443:443", "80:80"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
volumes:
  caddy_data:
```

```
# Caddyfile
troedel.example.org {
    reverse_proxy troedel:8099
}
```

Inside a home network without a public name, Caddy's `tls internal` or a
mesh VPN that provides certificates (Tailscale's `serve`, for instance)
does the same job.

`TROEDEL_TRUST_PROXY=true` makes Trödel believe the proxy's
`X-Forwarded-*` headers. Set it **only** behind a proxy that overwrites
them. Without a proxy, a client could use those headers to dodge the login
throttle.

HTTPS also unlocks the browser's clipboard and share features; over plain
HTTP Trödel falls back to an older way of copying.
