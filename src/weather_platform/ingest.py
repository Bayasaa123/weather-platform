"""Phase 1: fetch hourly weather + air quality from Open-Meteo and save as Parquet.

Run with:  uv run weather-ingest
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd


@dataclass(frozen=True)
class City:
    name: str
    latitude: float
    longitude: float
    timezone: str  # used later (dbt) to derive local time; we store UTC


CITIES: dict[str, City] = {
    "sydney": City("sydney", -33.8688, 151.2093, "Australia/Sydney"),
    "ulaanbaatar": City("ulaanbaatar", 47.9077, 106.8832, "Asia/Ulaanbaatar"),
}

# Each source = one Open-Meteo API + the hourly variables we want from it.
SOURCES: dict[str, dict] = {
    "weather": {
        "url": "https://api.open-meteo.com/v1/forecast",
        "hourly": [
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
        ],
    },
    "air_quality": {
        "url": "https://air-quality-api.open-meteo.com/v1/air-quality",
        "hourly": ["pm10", "pm2_5", "nitrogen_dioxide", "ozone", "us_aqi"],
    },
}

DEFAULT_BASE_DIR = Path("data/raw")


def build_params(city: City, hourly: list[str]) -> dict[str, str | float | int]:
    """Query parameters for an Open-Meteo request (yesterday + 2 forecast days, in UTC)."""
    return {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "hourly": ",".join(hourly),
        "timezone": "UTC",
        "past_days": 1,
        "forecast_days": 2,
    }


def fetch_json(
    client: httpx.Client,
    url: str,
    params: dict,
    retries: int = 3,
    backoff_seconds: float = 1.0,
) -> dict:
    """GET a URL and return the JSON body, retrying transient failures."""
    for attempt in range(1, retries + 1):
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPStatusError, httpx.TransportError):
            if attempt == retries:
                raise
            time.sleep(backoff_seconds * attempt)
    raise AssertionError("unreachable")


def to_dataframe(payload: dict, city: City, source: str, ingested_at: datetime) -> pd.DataFrame:
    """Turn Open-Meteo's column-oriented `hourly` block into one row per hour."""
    df = pd.DataFrame(payload["hourly"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df.insert(1, "city", city.name)
    df.insert(2, "latitude", city.latitude)
    df.insert(3, "longitude", city.longitude)
    df["source"] = source
    df["ingested_at"] = pd.Timestamp(ingested_at)
    return df


def write_parquet(
    df: pd.DataFrame, base_dir: Path, source: str, city: str, ingested_at: datetime
) -> Path:
    """Write to raw/{source}/ingest_date=YYYY-MM-DD/{city}_{HHMMSS}Z.parquet."""
    path = (
        base_dir
        / source
        / f"ingest_date={ingested_at:%Y-%m-%d}"
        / f"{city}_{ingested_at:%H%M%S}Z.parquet"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="pyarrow", index=False)
    return path


def summarize(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """One row per (city, source) with row count, time range and headline stats."""
    rows = []
    for df in frames:
        row = {
            "city": df["city"].iat[0],
            "source": df["source"].iat[0],
            "rows": len(df),
            "from_utc": df["time"].min().strftime("%Y-%m-%d %H:%M"),
            "to_utc": df["time"].max().strftime("%Y-%m-%d %H:%M"),
        }
        if "temperature_2m" in df:
            row["temp_min_c"] = df["temperature_2m"].min()
            row["temp_max_c"] = df["temperature_2m"].max()
            row["precip_total_mm"] = df["precipitation"].sum()
        if "pm2_5" in df:
            row["pm2_5_max"] = df["pm2_5"].max()
            row["us_aqi_max"] = df["us_aqi"].max()
        rows.append(row)
    return pd.DataFrame(rows)


def run(
    client: httpx.Client,
    base_dir: Path = DEFAULT_BASE_DIR,
    ingested_at: datetime | None = None,
) -> tuple[pd.DataFrame, list[Path]]:
    """Fetch every city × source, write Parquet, and return (summary, written paths)."""
    ingested_at = ingested_at or datetime.now(timezone.utc).replace(microsecond=0)
    frames: list[pd.DataFrame] = []
    paths: list[Path] = []
    for city in CITIES.values():
        for source, spec in SOURCES.items():
            payload = fetch_json(client, spec["url"], build_params(city, spec["hourly"]))
            df = to_dataframe(payload, city, source, ingested_at)
            paths.append(write_parquet(df, base_dir, source, city.name, ingested_at))
            frames.append(df)
    return summarize(frames), paths


def main() -> None:
    with httpx.Client(timeout=30.0) as client:
        summary, paths = run(client)
    print(summary.to_string(index=False, float_format=lambda x: f"{x:.1f}"))
    print(f"\nWrote {len(paths)} files:")
    for path in paths:
        print(f"  {path}")


if __name__ == "__main__":
    main()
