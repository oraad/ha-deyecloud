"""DataUpdateCoordinator for DeyeCloud."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api_types import (
    Device,
    MeasurePoint,
    OptimizerRecord,
    Station,
    StationCoordinatorData,
)
from .const import (
    DOMAIN,
    HISTORY_GRANULARITY_DAILY,
    LOGGER,
    OPTIMIZER_UPDATE_INTERVAL_SECONDS,
    UPDATE_INTERVAL_SECONDS,
    is_panel_optimizer,
    supports_latest_telemetry,
)
from .exceptions import DeyeCloudAuthError, DeyeCloudConnectionError, DeyeCloudError
from .optimizers import (
    is_optimizer_refresh_due,
    optimizer_average_power,
    optimizer_history_window,
    parse_optimizer_history,
    resolve_station_timezone,
)
from .subentry_sync import filter_stations_by_selection, normalize_station_id

if TYPE_CHECKING:
    from datetime import tzinfo

    from homeassistant.core import HomeAssistant

    from .api import DeyeCloudApiClient
    from .data import DeyeCloudConfigEntry


def _device_online(device: Device) -> bool:
    """
    Return whether an optimizer is believed to be producing.

    ``connectStatus`` is ``1`` when online; ``0`` and ``2`` (fault) mean it is
    not. An absent value is treated as online so a missing field cannot zero out
    the power average.
    """
    if device.connect_status is None:
        return True
    return device.connect_status == 1


def _local_timezone() -> tzinfo:
    """Return the Home Assistant timezone as a fallback."""
    return dt_util.DEFAULT_TIME_ZONE or UTC


class DeyeCloudCoordinator(DataUpdateCoordinator[dict[str, StationCoordinatorData]]):
    """Fetch and cache DeyeCloud station and device data."""

    config_entry: DeyeCloudConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: DeyeCloudConfigEntry) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )

    def _measure_points_for_devices(
        self, devices: list[Device]
    ) -> dict[str, list[MeasurePoint]]:
        cache = self.config_entry.runtime_data.measure_point_cache
        return {
            device.device_sn: list(cache.get(device.device_sn, []))
            for device in devices
        }

    def _telemetry_serials(self, devices: list[Device]) -> list[str]:
        """
        Return serials worth sending to /device/latest.

        Collectors and optimizers always answer with an empty
        ``deviceDataList``, so keeping them out of the batches leaves room for
        real devices inside the 10-serial request limit and avoids spending
        quota on calls that cannot return anything.
        """
        return [
            device.device_sn
            for device in devices
            if supports_latest_telemetry(device.device_type)
        ]

    async def _async_update_optimizers(
        self,
        client: DeyeCloudApiClient,
        station: Station,
        station_devices: list[Device],
        *,
        poll: bool,
        now_ts: float,
    ) -> dict[str, OptimizerRecord]:
        """
        Return derived optimizer production for one station.

        When ``poll`` is False the previous records are reused untouched, which
        is what keeps this off the hot path of the 3 minute live poll.
        """
        station_key = normalize_station_id(station.station_id) or station.station_id
        previous = (self.data or {}).get(station_key)
        previous_records = previous.optimizers if previous else {}

        optimizers = [
            device
            for device in station_devices
            if is_panel_optimizer(device.device_type)
        ]
        if not optimizers:
            return {}

        if not poll:
            return {
                device.device_sn: previous_records[device.device_sn]
                for device in optimizers
                if device.device_sn in previous_records
            }

        timezone_info = resolve_station_timezone(station.raw, _local_timezone())
        now = datetime.fromtimestamp(now_ts, tz=UTC)
        local_day, start_at = optimizer_history_window(now, timezone_info)
        state = self.config_entry.runtime_data.optimizer_state
        records: dict[str, OptimizerRecord] = {}

        async def fetch(device: Device) -> None:
            try:
                buckets = await client.async_get_device_history(
                    device.device_sn,
                    granularity=HISTORY_GRANULARITY_DAILY,
                    start_at=start_at,
                    end_at=local_day,
                )
            except DeyeCloudError:
                LOGGER.exception(
                    "Failed to fetch optimizer history for %s", device.device_sn
                )
                if (cached := previous_records.get(device.device_sn)) is not None:
                    records[device.device_sn] = cached
                return

            summary = parse_optimizer_history(buckets, day=local_day)
            derived = optimizer_average_power(
                state.get(device.device_sn),
                day=local_day,
                today_kwh=summary["today"],
                now_ts=now_ts,
                online=_device_online(device),
            )
            state[device.device_sn] = derived
            records[device.device_sn] = OptimizerRecord(
                device_sn=device.device_sn,
                date=summary["date"],
                today=derived["today"],
                month=summary["month"],
                power=derived["power"],
                online=_device_online(device),
            )

        await asyncio.gather(*(fetch(device) for device in optimizers))
        return records

    async def _async_update_data(self) -> dict[str, StationCoordinatorData]:
        runtime = self.config_entry.runtime_data
        client = runtime.client
        try:
            stations = await client.async_get_stations()
            stations = filter_stations_by_selection(stations, self.config_entry)
            if not stations:
                return {}

            now_ts = datetime.now(tz=UTC).timestamp()
            poll_optimizers = is_optimizer_refresh_due(
                runtime.optimizer_last_poll,
                now_ts,
                OPTIMIZER_UPDATE_INTERVAL_SECONDS,
            )
            if poll_optimizers:
                runtime.optimizer_last_poll = now_ts

            station_ids = [station.station_id for station in stations]
            devices = await client.async_get_station_devices(station_ids)
            devices_by_station: dict[str, list[Device]] = {}
            for device in devices:
                devices_by_station.setdefault(device.station_id, []).append(device)

            async def build_station_data(
                station: Station,
            ) -> tuple[str, StationCoordinatorData]:
                station_devices = devices_by_station.get(station.station_id, [])
                latest, station_latest, optimizers = await asyncio.gather(
                    client.async_get_device_latest(
                        self._telemetry_serials(station_devices)
                    ),
                    client.async_get_station_latest(station.station_id),
                    self._async_update_optimizers(
                        client,
                        station,
                        station_devices,
                        poll=poll_optimizers,
                        now_ts=now_ts,
                    ),
                )
                device_data = {item.device_sn: item for item in latest}

                return station.station_id, StationCoordinatorData(
                    info=station,
                    devices=station_devices,
                    device_data=device_data,
                    measure_points=self._measure_points_for_devices(station_devices),
                    station_latest=station_latest,
                    optimizers=optimizers,
                )

            results = await asyncio.gather(
                *(build_station_data(station) for station in stations)
            )
            self._prune_optimizer_state(
                {
                    serial
                    for _, station_data in results
                    for serial in station_data.optimizers
                }
            )
            return {
                normalize_station_id(station_id) or station_id: data
                for station_id, data in results
            }
        except DeyeCloudAuthError as exc:
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except DeyeCloudConnectionError as exc:
            raise UpdateFailed(str(exc)) from exc
        except DeyeCloudError as exc:
            raise UpdateFailed(str(exc)) from exc

    def _prune_optimizer_state(self, active_serials: set[str]) -> None:
        """Drop the open power window for optimizers that no longer exist."""
        state = self.config_entry.runtime_data.optimizer_state
        for serial in [sn for sn in state if sn not in active_serials]:
            del state[serial]
