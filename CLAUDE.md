# CLAUDE.md

Weather data platform: Open-Meteo (weather + air quality, Sydney & Ulaanbaatar) → GCS Parquet
→ BigQuery → dbt → Dagster → ntfy.sh. See `docs/architecture.md` and `docs/plan.md`.

**The user is learning.** Explain each step and the reasoning behind it as you work.
Do only the phase that was asked for.

## Hard constraints (never violate)
- GCP **Always Free tier** only. Region **us-central1** for every resource.
- BigQuery: **load jobs only** (no streaming inserts). Set `maximum_bytes_billed` on queries.
  Partition tables by date.
- At most **3 Cloud Scheduler jobs**.
- **No Secret Manager.** No service-account JSON keys. CI uses Workload Identity Federation.
- Keep the Docker image small, because Artifact Registry's free tier is only 0.5 GB.

## Cloud changes require approval
- **Never** run `terraform apply`, `terraform destroy`, or any `gcloud`/`bq` command that
  creates, modifies, or deletes cloud resources without asking the user first.
- Always show the plan first (e.g. `terraform plan` output, or the exact command and its
  effect) and wait for explicit approval before applying.
- Read-only commands (`terraform plan`, `gcloud ... list/describe`, `bq ls/show`) are fine.

## Commands
```bash
uv sync                      # install deps (Python 3.12, pinned in .python-version)
uv run weather-ingest        # Phase 1: fetch → data/raw/*.parquet + summary
uv run pytest -v             # tests (offline, mocked HTTP)
```

## Layout
- `src/weather_platform/`: Python package (`ingest.py` = Open-Meteo extraction)
- `tests/`: pytest
- `docs/`: architecture and phased plan
- `data/`: local output, git-ignored

## Conventions
- Store timestamps in **UTC**. Derive local time in dbt.
- snake_case columns, matching Open-Meteo variable names (`temperature_2m`, `pm2_5`, ...).
- Raw path layout: `raw/{source}/ingest_date=YYYY-MM-DD/{city}_{HHMMSS}Z.parquet`.
- Keep functions small and pure where possible, so tests don't need the network.
- Manage dependencies with uv (`uv add <pkg>`, `uv add --dev <pkg>`). Never use pip directly.
