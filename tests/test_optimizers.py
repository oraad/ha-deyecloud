"""Tests for optimizer history derivation helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from custom_components.deyecloud.optimizers import (
    is_optimizer_refresh_due,
    optimizer_average_power,
    optimizer_day_start,
    optimizer_history_window,
    optimizer_month_start,
    parse_optimizer_history,
    resolve_station_timezone,
)
from tests.conftest import load_fixture

DAY = "2026-09-28"


def _history(*pairs: tuple[str, str]) -> list[dict]:
    return [
        {
            "time": date,
            "itemList": [{"key": "Production", "value": value, "unit": "kWh"}],
        }
        for date, value in pairs
    ]


def test_parse_history_sums_month_and_reads_today() -> None:
    """Daily buckets give both today's total and the month-to-date total."""
    result = parse_optimizer_history(
        load_fixture("optimizer_history.json")["dataList"], day=DAY
    )
    assert result["date"] == DAY
    assert result["today"] == 0.42
    assert result["month"] == 7.7


def test_parse_history_today_defaults_to_zero_when_bucket_absent() -> None:
    """A month with no bucket for today yet reports zero, not unknown."""
    result = parse_optimizer_history(_history(("2026-09-26", "1.5")), day=DAY)
    assert result["today"] == 0.0
    assert result["month"] == 1.5


def test_parse_history_empty_response_is_distinct_from_zero() -> None:
    """An empty payload must not look like a genuine production of zero."""
    result = parse_optimizer_history([], day=DAY)
    assert result["date"] is None
    assert result["today"] is None
    assert result["month"] is None


def test_parse_history_empty_fixture() -> None:
    """The empty API fixture keeps every field unknown."""
    result = parse_optimizer_history(
        load_fixture("optimizer_history_empty.json")["dataList"], day=DAY
    )
    assert result["date"] is None


def test_parse_history_ignores_previous_month() -> None:
    """Buckets from the previous month are excluded from the month total."""
    result = parse_optimizer_history(
        _history(("2026-08-31", "9.9"), ("2026-09-28", "1.25")), day=DAY
    )
    assert result["month"] == 1.25
    assert result["today"] == 1.25


def test_parse_history_accepts_compact_dates() -> None:
    """Buckets labelled without separators are still understood."""
    result = parse_optimizer_history(_history(("20260928", "2.5")), day=DAY)
    assert result["today"] == 2.5


def test_parse_history_skips_malformed_buckets() -> None:
    """Unparseable labels and non-numeric values are dropped."""
    buckets = [
        {"time": "not-a-date", "itemList": [{"key": "Production", "value": "9"}]},
        {"time": "2026-09-27", "itemList": [{"key": "Production", "value": "n/a"}]},
        {"time": "2026-09-27", "itemList": []},
    ]
    result = parse_optimizer_history(buckets, day=DAY)
    assert result["date"] is None


def test_parse_history_uses_collection_time_fallback() -> None:
    """A collectionTime label is accepted when time is absent."""
    buckets = [
        {
            "collectionTime": "2026-09-28 12:00:00",
            "itemList": [{"key": "Production", "value": "1.0"}],
        }
    ]
    assert parse_optimizer_history(buckets, day=DAY)["today"] == 1.0


def test_average_power_seeds_on_first_sample() -> None:
    """The first sample of a day opens the window without reporting power."""
    state = optimizer_average_power(None, day=DAY, today_kwh=1.0, now_ts=1_000.0)
    assert state["power"] is None
    assert state["power_kwh"] == 1.0
    assert state["power_since"] == 1_000.0


def test_average_power_integrates_production_growth() -> None:
    """A known kWh gain over a known interval yields an average wattage."""
    seed = optimizer_average_power(None, day=DAY, today_kwh=1.0, now_ts=1_000.0)
    state = optimizer_average_power(seed, day=DAY, today_kwh=1.9, now_ts=1_600.0)
    # 0.9 kWh over 600 s -> 0.9 * 3_600_000 / 600 W, i.e. a 5.4 kW array.
    assert state["power"] == 5400.0


def test_average_power_holds_value_through_flat_production() -> None:
    """Flat production keeps the last average so coarse kWh steps do not read zero."""
    seed = optimizer_average_power(None, day=DAY, today_kwh=1.0, now_ts=1_000.0)
    grown = optimizer_average_power(seed, day=DAY, today_kwh=1.9, now_ts=1_600.0)
    flat = optimizer_average_power(grown, day=DAY, today_kwh=1.9, now_ts=2_000.0)
    assert flat["power"] == grown["power"]


def test_average_power_reports_zero_after_idle_window() -> None:
    """A sustained flat series eventually reports zero watts."""
    seed = optimizer_average_power(None, day=DAY, today_kwh=1.0, now_ts=1_000.0)
    grown = optimizer_average_power(seed, day=DAY, today_kwh=1.9, now_ts=1_600.0)
    idle = optimizer_average_power(
        grown, day=DAY, today_kwh=1.9, now_ts=1_600.0 + 3_601
    )
    assert idle["power"] == 0.0


def test_average_power_reopens_window_on_new_day() -> None:
    """Midnight resets the counter, so the window must restart."""
    seed = optimizer_average_power(
        None, day="2026-09-27", today_kwh=9.0, now_ts=1_000.0
    )
    rolled = optimizer_average_power(
        seed, day="2026-09-28", today_kwh=0.2, now_ts=86_500.0
    )
    assert rolled["power"] is None
    assert rolled["power_kwh"] == 0.2
    assert rolled["date"] == "2026-09-28"


def test_average_power_reopens_window_on_counter_reset() -> None:
    """A backwards counter within one day is treated as a reset, not a huge gain."""
    seed = optimizer_average_power(None, day=DAY, today_kwh=5.0, now_ts=1_000.0)
    rolled = optimizer_average_power(seed, day=DAY, today_kwh=0.1, now_ts=1_600.0)
    assert rolled["power"] is None
    assert rolled["power_kwh"] == 0.1


def test_average_power_offline_reports_zero_and_rebases() -> None:
    """An offline optimizer reports zero and rebases so recovery cannot spike."""
    seed = optimizer_average_power(None, day=DAY, today_kwh=1.0, now_ts=1_000.0)
    grown = optimizer_average_power(seed, day=DAY, today_kwh=1.9, now_ts=1_600.0)
    offline = optimizer_average_power(
        grown, day=DAY, today_kwh=1.9, now_ts=2_000.0, online=False
    )
    assert offline["power"] == 0.0
    recovered = optimizer_average_power(offline, day=DAY, today_kwh=2.4, now_ts=2_600.0)
    # 0.5 kWh over the 600 s since the offline baseline, not 0.5 over 1600 s.
    assert recovered["power"] == 3000.0


def test_average_power_holds_state_when_today_is_unknown() -> None:
    """A missing reading leaves the previous window untouched."""
    seed = optimizer_average_power(None, day=DAY, today_kwh=1.0, now_ts=1_000.0)
    grown = optimizer_average_power(seed, day=DAY, today_kwh=1.9, now_ts=1_600.0)
    held = optimizer_average_power(grown, day=DAY, today_kwh=None, now_ts=2_000.0)
    assert held["power"] == grown["power"]
    assert held["power_since"] == grown["power_since"]


def test_average_power_ignores_non_positive_interval() -> None:
    """A clock that did not advance cannot produce an infinite average."""
    seed = optimizer_average_power(None, day=DAY, today_kwh=1.0, now_ts=1_000.0)
    state = optimizer_average_power(seed, day=DAY, today_kwh=1.9, now_ts=1_000.0)
    assert state["power"] is None


@pytest.mark.parametrize(
    ("region", "expected_offset"),
    [
        ("UTC", 0),
        ("Etc/UTC", 0),
        ("Asia/Kolkata", 5.5),
        ("Europe/Berlin", 2),
        ("+05:30", 5.5),
        ("-08:00", -8),
        ("UTC+2", 2),
    ],
)
def test_resolve_station_timezone(region: str, expected_offset: float) -> None:
    """IANA names and raw UTC offsets both resolve to the plant timezone."""
    resolved = resolve_station_timezone({"regionTimezone": region})
    offset = resolved.utcoffset(datetime(2026, 9, 28, tzinfo=resolved))
    assert offset == timedelta(hours=expected_offset)


@pytest.mark.parametrize("region", ["", "   ", "Not/AZone", None, 42])
def test_resolve_station_timezone_falls_back(region: object) -> None:
    """An unusable region falls back rather than raising."""
    fallback = timezone(timedelta(hours=3))
    assert resolve_station_timezone({"regionTimezone": region}, fallback) is fallback
    assert resolve_station_timezone(None, fallback) is fallback
    assert resolve_station_timezone({}, fallback) is fallback


def test_resolve_station_timezone_defaults_to_utc() -> None:
    """With no station payload at all the helper still returns a timezone."""
    assert resolve_station_timezone(None) is UTC


def test_history_window_uses_plant_local_day() -> None:
    """The local day and month start follow the plant, not the caller."""
    # 22:00 UTC on the 28th is already the 29th in Kolkata (UTC+05:30).
    now = datetime(2026, 9, 28, 22, 0, tzinfo=UTC)
    day, start_at = optimizer_history_window(
        now, resolve_station_timezone({"regionTimezone": "Asia/Kolkata"})
    )
    assert day == "2026-09-29"
    assert start_at == "2026-09-01"


def test_period_start_helpers_are_timezone_aware() -> None:
    """Day and month boundaries carry the plant timezone for last_reset."""
    kolkata = resolve_station_timezone({"regionTimezone": "Asia/Kolkata"})
    day_start = optimizer_day_start(DAY, kolkata)
    month_start = optimizer_month_start(DAY, kolkata)
    assert day_start is not None and day_start.utcoffset() == timedelta(
        hours=5, minutes=30
    )
    assert month_start is not None and month_start.day == 1
    assert day_start is not None and day_start.day == 28


def test_period_start_helpers_tolerate_missing_day() -> None:
    """A record without a date yields no reset point."""
    assert optimizer_day_start(None, UTC) is None
    assert optimizer_month_start("not-a-date", UTC) is None


@pytest.mark.parametrize(
    ("last_ts", "elapsed", "due"),
    [
        (None, 0, True),
        (1_000.0, 899, False),
        (1_000.0, 900, True),
        (1_000.0, 5_000, True),
    ],
)
def test_is_optimizer_refresh_due(
    last_ts: float | None, elapsed: int, due: bool
) -> None:
    """The optimizer poll is gated at the configured interval."""
    assert is_optimizer_refresh_due(last_ts, 1_000.0 + elapsed, 900) is due
