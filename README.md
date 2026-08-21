# Job Application Tracker

Personal Docker service for a Raspberry Pi 4. Polls Gmail `Updates` every 30 minutes, extracts recruiting facts on a Colab T4 (Qwen2.5-7B 4-bit, weights cached on Google Drive), and shows applications in a plain HTML table.

## Architecture

- **worker**: Gmail poller + Colab CLI orchestration + SQLite writes
- **web**: FastAPI table UI on port `8080` (read-only SQLite)

## Prerequisites

- Raspberry Pi 4 with Docker and Docker Compose
- Google account with Gmail and Google Drive (same account used for Colab Pro)
- Colab Pro (or pay-as-you-go compute units) for T4 sessions

## One-time Google Cloud setup (Gmail API)

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project.
3. Enable **Gmail API**.
4. Configure the OAuth consent screen (External is fine for personal use).
5. Create credentials: **OAuth client ID** -> Application type **Desktop app**.
6. Download the JSON and save it as `secrets/credentials.json` in this repo.

```bash
mkdir -p secrets data
# place credentials.json under secrets/
```

## Build

On the Pi (arm64):

```bash
cd /path/to/job_applications_tracking
docker compose build
```

## Auth: Gmail

```bash
docker compose run --rm -it worker python -m worker.gmail_auth
```

This opens a browser OAuth flow and writes `secrets/token.json`.

## Auth: Colab CLI

```bash
docker compose run --rm -it worker colab --auth oauth2 sessions
```

Follow the printed URL, paste the authorization code back into the terminal. State is stored in the Compose volume `colab_config`.

## First Drive mount

The first inference job runs `colab drivemount`. Complete the consent URL when prompted. Model weights are stored under:

`MyDrive/jobtrack/huggingface`

Later runs reuse that cache (no Hugging Face re-download).

## Run

```bash
docker compose up -d
```

Open `http://<pi-ip>:8080`.

Health check: `http://<pi-ip>:8080/healthz`.

## Behaviour

1. On first start, backfill: Gmail `category:updates newer_than:30d`.
2. ATS/keyword prefilter skips non-recruiting Updates mail (no Colab cost).
3. Matching messages are sent to Colab in chunks of 20.
4. Session lifecycle: `colab new` (T4) -> `drivemount` -> upload batch + script -> `exec` -> `stop`.
5. Every 30 minutes: Gmail history for `CATEGORY_UPDATES`, with `newer_than:1d` fallback if history is stale.
6. Missing fields stay empty. The model is instructed not to invent values.

## Environment variables (worker)

| Variable | Default | Meaning |
| --- | --- | --- |
| `JOBTRACK_DB_PATH` | `/data/jobtrack.db` | SQLite path |
| `GMAIL_CREDENTIALS_PATH` | `/secrets/credentials.json` | OAuth client JSON |
| `GMAIL_TOKEN_PATH` | `/secrets/token.json` | Stored user token |
| `POLL_INTERVAL_SECONDS` | `1800` | Poll interval |
| `COLAB_SESSION_NAME` | `jobtrack` | Colab session name |
| `BATCH_SIZE` | `20` | Messages per Colab run |
| `LOG_LEVEL` | `INFO` | Logging level |

## Logs

```bash
docker compose logs -f worker
docker compose logs -f web
```

## Stop

```bash
docker compose down
```

If a Colab session was left running after a crash, the worker stops leftover `jobtrack` sessions on start and on shutdown.
