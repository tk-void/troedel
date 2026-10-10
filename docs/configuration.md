# Configuration

What you change while using Trödel is in **Settings** in the app: texts for
pickup and shipping, the default photo look, the AI provider, the password,
the fill helper.

What belongs to the installation comes from the environment, or from flags
of the `troedel` command.

| Variable | Default | Meaning |
|---|---|---|
| `TROEDEL_DATA_DIR` | `./data` (`/data` in the image) | Database, photos, models, API key. Also `--data-dir`. |
| `TROEDEL_HOST` | `127.0.0.1` (`0.0.0.0` in the image) | Address to listen on. Also `--host`. Loopback by default: reaching Trödel from another device is a decision. |
| `TROEDEL_PORT` | `8099` | Also `--port`. |
| `TROEDEL_TRUST_PROXY` | `false` | Believe `X-Forwarded-Proto`, `-Host` and `-For`. Only behind a reverse proxy that sets them; see [security.md](security.md). |
| `TROEDEL_SETUP_CODE` | random | Fixes the one-time setup code instead of printing a random one, for unattended installs. |
| `TROEDEL_PROVIDER` | – | `anthropic`, `gemini`, `openai`, `ollama`, `custom` or `claude-cli`. Set here, it is locked in the app. |
| `TROEDEL_MODEL` | provider default | Model name. |
| `TROEDEL_BASE_URL` | provider default | Address of an OpenAI-compatible service. |
| `TROEDEL_API_KEY_FILE` | – | Path of a file holding the API key. Prefer this over the next one: a variable shows up in `docker inspect` and in process listings. |
| `TROEDEL_API_KEY` | – | The API key itself, for quick local runs. |
| `TROEDEL_CUTOUT` | on if installed | `false` switches photo editing off even when the `cutout` extra is installed. |
| `TROEDEL_CUTOUT_MODEL` | `birefnet-general-lite` | Any model name `rembg` knows. |
| `TROEDEL_MAX_PHOTOS` | `12` | Photos per item. |
| `TROEDEL_ANALYSIS_PHOTOS` | `4` | How many of them the AI provider gets to see. |

## Commands

```
troedel                    start the server
troedel reset-password     forget the password; prints a new setup code
troedel version
```

## Updating

Replace the package or image and start again. The database migrates itself
on start and refuses to open if it was written by a newer version. Copy the
data directory before an update if you want a way back.
