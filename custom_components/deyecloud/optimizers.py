"""
Derivation helpers for DeyeCloud panel optimizers.

Optimizers expose no live telemetry: ``/device/latest`` returns an empty
``deviceDataList`` and ``/device/measurePoints`` answers ``device not
supported``. The only usable series is ``Production`` (kWh) from
``/device/history``, which rolls up once a day and therefore moves in coarse
0.01 kWh steps.

Because the series is a cumulative daily total, instantaneous power has to be
reconstructed by integrating the growth of ``Production Today`` over an open
window. Every function here is pure so the behaviour can be tested without a
running Home Assistant instance.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .const import OPTIMIZER_IDLE_SECONDS

# W = kWh * 1000 Wh/kWh * 3600 s/h / elapsed_s, so dividing a kWh delta by a
# second count needs this factor rather than the plain kWh-to-Wh constant.
_KWH_TO_WH_PER_SECOND = 3_600_000.0

_OFFSET_RE = re.compile(
    r"^(?:UTC|GMT)?\s*(?P<sign>[+-])(?P<hours>\d{1,2})(?::?(?P<minutes>\d{2}))?$",
    re.IGNORECASE,
)

_COMPACT_DATE_RE = re.compile(r"^\d{8}$")


def resolve_station_timezone(
    station_raw: dict[str, Any] | None,
    fallback: tzinfo | None = None,
) -> tzinfo:
    """
    Return the plant timezone described by a station payload.

    Daily history buckets are cut on the *plant's* local midnight, not the
    Home Assistant timezone, so ``regionTimezone`` is required for
    ``Production Today`` to mean the right thing.
    """
    region = (station_raw or {}).get("regionTimezone")
    if isinstance(region, str):
        text = region.strip()
        if text:
            if text.upper() in {"UTC", "GMT", "Z"}:
                return UTC
            if (parsed := _parse_utc_offset(text)) is not None:
                return parsed
            try:
                return ZoneInfo(text)
            except ZoneInfoNotFoundError, ValueError, KeyError:
                pass
    return fallback or UTC


def _parse_utc_offset(text: str) -> tzinfo | None:
    match = _OFFSET_RE.match(text)
    if match is None:
        return None
    hours = int(match.group("hours"))
    minutes = int(match.group("minutes") or 0)
    if hours > 23 or minutes > 59:
        return None
    delta = timedelta(hours=hours, minutes=minutes)
    if match.group("sign") == "-":
        delta = -delta
    return timezone(delta)


def _bucket_date(raw: Any) -> str | None:
    """
    Normalize a history bucket label to ``YYYY-MM-DD``.

    The API has been observed returning both ``2026-09-28`` and ``20260928``,
    optionally with a time component, so the label is parsed defensively.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return _compact_to_iso(str(int(raw)))
    text = str(raw).strip()
    if not text:
        return None
    if _COMPACT_DATE_RE.match(text):
        return _compact_to_iso(text)
    head = text[:10]
    if len(head) != 10 or head[4] != "-" or head[7] != "-":
        return None
    return head


def _compact_to_iso(text: str) -> str | None:
    if not _COMPACT_DATE_RE.match(text):
        return None
    return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"


def parse_optimizer_history(
    data_list: list[dict[str, Any]] | None,
    *,
    day: str,
) -> dict[str, Any]:
    """
    Summarise a daily ``Production`` history response for one optimizer.

    ``day`` is the current local calendar day at the plant. Returns ``today``
    (kWh) and ``month`` (kWh so far this local month). ``date`` is ``None``
    when the API returned no usable bucket at all, which is deliberately kept
    distinct from a genuine production of ``0``.
    """
    empty: dict[str, Any] = {
        "date": None,
        "today": None,
        "month": None,
        "online": True,
    }
    if not data_list:
        return empty

    month_prefix = day[:7]
    today: float | None = None
    month = 0.0
    seen_month = False

    for bucket in data_list:
        bucket_date = _bucket_date(bucket.get("time") or bucket.get("collectionTime"))
        if bucket_date is None:
            continue
        value = _production_value(bucket)
        if value is None:
            continue
        if bucket_date[:7] == month_prefix:
            month += value
            seen_month = True
        if bucket_date == day:
            today = value

    if not seen_month:
        return empty

    return {
        "date": day,
        "today": today if today is not None else 0.0,
        "month": round(month, 2),
        "online": True,
    }


def _production_value(bucket: dict[str, Any]) -> float | None:
    for item in bucket.get("itemList") or []:
        if not isinstance(item, dict) or item.get("key") != "Production":
            continue
        value = _to_float(item.get("value"))
        if value is not None:
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except TypeError, ValueError:
        return None


def optimizer_average_power(
    previous: dict[str, Any] | None,
    *,
    day: str,
    today_kwh: float | None,
    now_ts: float,
    online: bool = True,
    idle_seconds: int = OPTIMIZER_IDLE_SECONDS,
) -> dict[str, Any]:
    """
    Reconstruct average power from the growth of ``Production Today``.

    ``previous`` is the prior state for this optimizer. The returned mapping
    always carries a usable ``power`` (or ``None`` while the window is still
    seeding) plus the fields needed to continue the calculation on the next
    poll.

    Two baselines are tracked. ``power_kwh``/``power_since`` anchor the running
    average, so ``power`` is the mean output since the window opened. The
    separate ``last_kwh``/``last_change_ts`` pair is what distinguishes "still
    producing" from "flat", which is what lets a flat series hold its last
    average instead of decaying towards zero.

    The window is dropped when the optimizer goes offline or the cumulative
    counter moves backwards, so a reconnect cannot produce a single enormous
    spike by integrating across an outage.
    """
    state: dict[str, Any] = {
        "date": day,
        "today": today_kwh,
        "power": None,
        "power_since": now_ts,
        "power_kwh": today_kwh,
        "last_kwh": today_kwh,
        "last_change_ts": now_ts,
    }
    if previous:
        for key in ("power", "power_since", "power_kwh", "last_kwh", "last_change_ts"):
            if key in previous:
                state[key] = previous[key]
        state["today"] = today_kwh

    if not online:
        return _reseed(state, day=day, today_kwh=today_kwh, now_ts=now_ts, power=0.0)

    if today_kwh is None:
        # No reading for today yet; hold the last known values untouched.
        return state

    baseline_kwh = state.get("power_kwh")
    baseline_since = state.get("power_since")
    last_kwh = state.get("last_kwh")
    if state.get("date") != day:
        return _reseed(state, day=day, today_kwh=today_kwh, now_ts=now_ts)
    if not isinstance(baseline_kwh, (int, float)) or not isinstance(
        last_kwh, (int, float)
    ):
        return _reseed(state, day=day, today_kwh=today_kwh, now_ts=now_ts)
    if not isinstance(baseline_since, (int, float)):
        return _reseed(state, day=day, today_kwh=today_kwh, now_ts=now_ts)

    delta = today_kwh - last_kwh
    if delta < 0:
        # Counter reset inside the same day; the baseline is no longer valid.
        return _reseed(state, day=day, today_kwh=today_kwh, now_ts=now_ts)

    if delta > 0:
        # Still producing: refresh the running average over the whole window.
        elapsed = now_ts - baseline_since
        if elapsed > 0:
            state["power"] = round(
                (today_kwh - baseline_kwh) * _KWH_TO_WH_PER_SECOND / elapsed, 1
            )
            state["last_change_ts"] = now_ts
        state["last_kwh"] = today_kwh
        return state

    # Flat production: keep the last average so that the coarse 0.01 kWh
    # resolution does not make a generating array read as zero, and only
    # report zero once the array has genuinely been idle.
    last_change = state.get("last_change_ts")
    if isinstance(last_change, (int, float)) and now_ts - last_change > idle_seconds:
        state["power"] = 0.0
    return state


def _reseed(
    state: dict[str, Any],
    *,
    day: str,
    today_kwh: float | None,
    now_ts: float,
    power: float | None = None,
) -> dict[str, Any]:
    state.update(
        {
            "date": day,
            "today": today_kwh,
            "power": power,
            "power_since": now_ts,
            "power_kwh": today_kwh,
            "last_kwh": today_kwh,
            "last_change_ts": now_ts,
        }
    )
    return state


def optimizer_history_window(
    now: datetime,
    timezone_info: tzinfo,
) -> tuple[str, str]:
    """
    Return ``(local_day, start_at)`` for the plant.

    The window starts at the first of the local month so that a single
    ``granularity=2`` response covers both ``Production Today`` and the
    month-to-date total. ``start_at`` is an inclusive date, matching the
    ``startAt`` format the OpenAPI expects.
    """
    local = now.astimezone(timezone_info)
    today = local.date()
    return today.isoformat(), date(today.year, today.month, 1).isoformat()


def is_optimizer_refresh_due(
    last_ts: float | None,
    now_ts: float,
    interval_seconds: int,
) -> bool:
    """Return True when the throttled optimizer poll should run."""
    if last_ts is None:
        return True
    return now_ts - last_ts >= interval_seconds


def optimizer_day_start(day: str | None, timezone_info: tzinfo) -> datetime | None:
    """Return the aware local midnight starting ``day``."""
    parsed = _parse_day(day)
    if parsed is None:
        return None
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone_info)


def optimizer_month_start(day: str | None, timezone_info: tzinfo) -> datetime | None:
    """Return the aware local midnight starting the month that contains ``day``."""
    parsed = _parse_day(day)
    if parsed is None:
        return None
    return datetime(parsed.year, parsed.month, 1, tzinfo=timezone_info)


def _parse_day(day: str | None) -> date | None:
    if not day:
        return None
    try:
        return date.fromisoformat(day)
    except ValueError:
        return None
