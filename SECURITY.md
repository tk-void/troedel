# Security policy

## Reporting a vulnerability

Please do **not** open a public issue for a security problem. Use GitHub's
private reporting instead: *Security → Report a vulnerability* on the
repository page. Describe what you found and how to reproduce it.

This is a spare-time project. You will get an answer as soon as time allows,
usually within two weeks, and credit in the release notes if you want it.

## What counts

Trödel is built for a home network, behind a password. Reports are welcome
for anything that breaks that model, for example:

- reaching listings, photos or settings without a valid login,
- acting with someone's session from another website,
- reading the API key through the app,
- escaping the photo directory, or making the server fetch or run something
  it should not,
- the fill helper's token reaching more than its own routes.

Known and accepted, documented in [docs/security.md](docs/security.md):
without HTTPS in front, traffic including the password is readable on the
network; and whoever can read the data directory can read everything in it.

## Supported versions

Only the latest release gets fixes.
