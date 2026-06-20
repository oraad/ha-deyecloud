"""DataUpdateCoordinator for DeyeCloud."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api_types import Device, MeasurePoint, Station, StationCoordinatorData
from .const import DOMAIN, LOGGER, UPDATE_INTERVAL_SECONDS
from .exceptions import DeyeCloudAuthError, DeyeCloudConnectionError, DeyeCloudError
from .subentry_sync import filter_stations_by_selection, normalize_station_id

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import DeyeCloudConfigEntry


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

    async def _async_update_data(self) -> dict[str, StationCoordinatorData]:
        client = self.config_entry.runtime_data.client
        try:
            stations = await client.async_get_stations()
            stations = filter_stations_by_selection(stations, self.config_entry)
            if not stations:
                return {}

            station_ids = [station.station_id for station in stations]
            devices = await client.async_get_station_devices(station_ids)
            devices_by_station: dict[str, list[Device]] = {}
            for device in devices:
                devices_by_station.setdefault(device.station_id, []).append(device)

            async def build_station_data(
                station: Station,
            ) -> tuple[str, StationCoordinatorData]:
                station_devices = devices_by_station.get(station.station_id, [])
                device_sns = [device.device_sn for device in station_devices]
                latest, station_latest = await asyncio.gather(
                    client.async_get_device_latest(device_sns),
                    client.async_get_station_latest(station.station_id),
                )
                device_data = {item.device_sn: item for item in latest}

                return station.station_id, StationCoordinatorData(
                    info=station,
                    devices=station_devices,
                    device_data=device_data,
                    measure_points=self._measure_points_for_devices(station_devices),
                    station_latest=station_latest,
                )

            results = await asyncio.gather(
                *(build_station_data(station) for station in stations)
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
