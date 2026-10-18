# weather-platform

A data platform for hourly weather and air quality in Sydney and Ulaanbaatar,
built on the GCP Always Free tier. See [docs/architecture.md](docs/architecture.md)
and [docs/plan.md](docs/plan.md).

## Quickstart

```bash
uv sync
uv run weather-ingest   # writes data/raw/**/*.parquet and prints a summary
uv run pytest -v
```
