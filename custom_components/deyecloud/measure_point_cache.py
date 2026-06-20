"""Measure point catalog cache for DeyeCloud devices."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .api_types import DataPoint, Device, MeasurePoint, StationCoordinatorData
from .exceptions import DeyeCloudError

if TYPE_CHECKING:
    from .api import DeyeCloudApiClient
    from .data import DeyeCloudConfigEntry

_LOGGER = logging.getLogger(__name__)
_MEASURE_POINT_FETCH_CONCURRENCY = 5
_PERMANENT_MEASURE_POINT_ERRORS = (
    "device not supported",
    "device no upload records found",
)


def _is_permanent_measure_point_error(error: DeyeCloudError) -> bool:
    """Return True when the API will never expose a measurePoints catalog."""
    message = str(error).lower()
    return any(item in message for item in _PERMANENT_MEASURE_POINT_ERRORS)


def iter_device_measure_specs(
    device_sn: str,
    station_data: StationCoordinatorData,
) -> list[tuple[str, str | None]]:
    """Return union of catalog and latest measure keys with resolved units."""
    catalog = {
        point.key: point for point in station_data.measure_points.get(device_sn, [])
    }
    latest_points: dict[str, DataPoint] = {}
    device_data = station_data.device_data.get(device_sn)
    if device_data:
        latest_points = {point.key: point for point in device_data.data_list}

    specs: list[tuple[str, str | None]] = []
    for key in sorted(set(catalog) | set(latest_points)):
        catalog_point = catalog.get(key)
        latest_point = latest_points.get(key)
        unit = None
        if catalog_point and catalog_point.unit:
            unit = catalog_point.unit
        elif latest_point and latest_point.unit:
            unit = latest_point.unit
        specs.append((key, unit))
    return specs


def apply_measure_point_cache_to_coordinator(entry: DeyeCloudConfigEntry) -> None:
    """Copy runtime catalog cache into coordinator station payloads."""
    cache = entry.runtime_data.measure_point_cache
    for station in entry.runtime_data.coordinator.data.values():
        station.measure_points = {
            device.device_sn: list(cache.get(device.device_sn, []))
            for device in station.devices
        }


def prune_measure_point_cache(entry: DeyeCloudConfigEntry) -> None:
    """Drop catalog entries for devices no longer present."""
    active_sns = {
        device.device_sn
        for station in entry.runtime_data.coordinator.data.values()
        for device in station.devices
    }
    cache = entry.runtime_data.measure_point_cache
    for device_sn in list(cache):
        if device_sn not in active_sns:
            del cache[device_sn]


async def _fetch_measure_points_with_limit(
    client: DeyeCloudApiClient,
    device_sn: str,
    semaphore: asyncio.Semaphore,
) -> list[MeasurePoint]:
    """Fetch measure points for one device with concurrency limiting."""
    async with semaphore:
        return await client.async_get_device_measure_points(device_sn)


async def async_refresh_measure_point_cache(
    entry: DeyeCloudConfigEntry,
    devices: list[Device],
) -> None:
    """Fetch measure point catalogs for devices missing from the runtime cache."""
    cache = entry.runtime_data.measure_point_cache
    client = entry.runtime_data.client
    missing = [device for device in devices if device.device_sn not in cache]
    if not missing:
        return

    semaphore = asyncio.Semaphore(_MEASURE_POINT_FETCH_CONCURRENCY)
    results = await asyncio.gather(
        *(
            _fetch_measure_points_with_limit(client, device.device_sn, semaphore)
            for device in missing
        ),
        return_exceptions=True,
    )
    for device, result in zip(missing, results, strict=True):
        if isinstance(result, BaseException):
            if isinstance(result, DeyeCloudError):
                if _is_permanent_measure_point_error(result):
                    _LOGGER.debug(
                        "Measure point catalog unavailable for %s: %s",
                        device.device_sn,
                        result,
                    )
                    cache[device.device_sn] = []
                else:
                    _LOGGER.warning(
                        "Measure point catalog fetch failed for %s: %s",
                        device.device_sn,
                        result,
                    )
            else:
                _LOGGER.exception(
                    "Unexpected error fetching measure points for %s",
                    device.device_sn,
                    exc_info=result,
                )
            continue
        cache[device.device_sn] = result
