from datetime import datetime, timezone

import httpx
import pandas as pd
import pytest

from weather_platform.ingest import (
    CITIES,
    fetch_json,
    run,
    to_dataframe,
    write_parquet,
)

INGESTED_AT = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)

# Small payloads shaped like real Open-Meteo responses (column arrays under "hourly").
WEATHER_PAYLOAD = {
    "hourly": {
        "time": ["2026-10-18T00:00", "2026-10-18T01:00", "2026-10-18T02:00"],
        "temperature_2m": [15.0, 14.5, 14.2],
        "relative_humidity_2m": [70, 72, 75],
        "apparent_temperature": [14.0, 13.6, 13.1],
        "precipitation": [0.0, 0.2, 0.0],
        "weather_code": [1, 61, 2],
        "wind_speed_10m": [10.1, 12.3, 9.8],
    }
}
AIR_PAYLOAD = {
    "hourly": {
        "time": ["2026-10-18T00:00", "2026-10-18T01:00", "2026-10-18T02:00"],
        "pm10": [12.0, 14.0, 13.0],
        "pm2_5": [5.0, 6.5, 6.0],
        "nitrogen_dioxide": [8.0, 9.0, 7.5],
        "ozone": [40.0, 42.0, 41.0],
        "us_aqi": [22, 27, 25],
    }
}


def mock_client(status_code: int = 200) -> httpx.Client:
    """An httpx client that never touches the network: it answers by hostname."""

    def handler(request: httpx.Request) -> httpx.Response:
        if status_code != 200:
            return httpx.Response(status_code)
        if request.url.host.startswith("air-quality"):
            return httpx.Response(200, json=AIR_PAYLOAD)
        return httpx.Response(200, json=WEATHER_PAYLOAD)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_to_dataframe_shapes_rows():
    df = to_dataframe(WEATHER_PAYLOAD, CITIES["sydney"], "weather", INGESTED_AT)

    assert len(df) == 3
    assert {"time", "city", "latitude", "longitude", "source", "ingested_at", "temperature_2m"} <= set(df.columns)
    assert (df["city"] == "sydney").all()
    assert str(df["time"].dt.tz) == "UTC"


def test_write_parquet_uses_hive_path_and_round_trips(tmp_path):
    df = to_dataframe(AIR_PAYLOAD, CITIES["ulaanbaatar"], "air_quality", INGESTED_AT)

    path = write_parquet(df, tmp_path, "air_quality", "ulaanbaatar", INGESTED_AT)

    assert path == tmp_path / "air_quality" / "ingest_date=2026-10-18" / "ulaanbaatar_120000Z.parquet"
    pd.testing.assert_frame_equal(pd.read_parquet(path), df)


def test_run_writes_one_file_per_city_and_source(tmp_path):
    summary, paths = run(mock_client(), base_dir=tmp_path, ingested_at=INGESTED_AT)

    assert len(paths) == 4
    assert all(p.exists() for p in paths)
    assert len(summary) == 4
    assert set(summary["city"]) == {"sydney", "ulaanbaatar"}
    assert set(summary["source"]) == {"weather", "air_quality"}


def test_fetch_json_raises_after_retries():
    with pytest.raises(httpx.HTTPStatusError):
        fetch_json(mock_client(500), "https://api.open-meteo.com/v1/forecast", {}, backoff_seconds=0)
