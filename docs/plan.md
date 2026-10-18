# Phased plan

Each phase ends with something that runs and is tested before moving on.

## Phase 1: Local ingestion ✅ (current)
- Python script fetches hourly weather and air quality for Sydney and Ulaanbaatar from Open-Meteo.
- Saves Parquet to `data/raw/` using the Hive-style layout from `architecture.md`.
- Prints a summary table.
- pytest tests that run offline, using a mocked HTTP transport.

## Phase 2: Terraform foundation
- Remote state bucket (bootstrap).
- GCS data bucket with a lifecycle rule.
- BigQuery datasets: `raw`, `staging`, `marts`.
- Service accounts: pipeline runtime and GitHub deployer, each with least-privilege roles.
- Artifact Registry repo with a cleanup policy.
- Workload Identity Federation pool and provider restricted to this GitHub repo.

## Phase 3: Cloud landing
- Upload Parquet to GCS.
- BigQuery load jobs into date-partitioned `raw` tables.
- Idempotent: re-running replaces the affected partitions.

## Phase 4: dbt
- dbt-bigquery project.
- `maximum_bytes_billed` set in the profile.
- Staging models: types, deduplication by (city, time) keeping the latest `ingested_at`, local time.
- Marts: daily city summary, latest conditions, alert candidates.
- dbt tests: not_null, unique, accepted ranges.

## Phase 5: Dagster
- Assets for ingest → GCS → BigQuery load.
- dbt models exposed as assets via `dagster-dbt`.
- Asset checks: row counts, freshness, value ranges.
- Docker Compose for local development with the Dagster UI.

## Phase 6: Deploy
- Dockerfile using a slim multi-stage build to stay under the 0.5 GB Artifact Registry free tier.
- Cloud Run Job in Terraform.
- 3 Cloud Scheduler jobs: hourly pipeline, Sydney brief, Ulaanbaatar brief.
- GitHub Actions: test, then build, push, and update the job. Authentication uses WIF.

## Phase 7: Notifications
- ntfy.sh morning brief per city, sent at about 07:00 local time.
- Threshold alerts in the hourly run for heavy rain, high PM2.5/AQI, and extreme temperature.
- Dedup so the same alert isn't sent every hour.
