"""Tests for measure point catalog cache."""

from __future__ import annotations

from unittest.mock import AsyncMock

from custom_components.deyecloud.api_types import (
    DataPoint,
    Device,
    DeviceData,
    MeasurePoint,
    Station,
    StationCoordinatorData,
    StationData,
)
from custom_components.deyecloud.data import DeyeCloudRuntimeData
from custom_components.deyecloud.measure_point_cache import (
    async_refresh_measure_point_cache,
    iter_device_measure_specs,
)
from custom_components.deyecloud.sensor import _build_station_entities


async def test_refresh_measure_point_cache_fetches_missing_only(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Catalog is fetched only for devices missing from the runtime cache."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    runtime = DeyeCloudRuntimeData(client=mock_api_client, coordinator=coordinator)
    mock_config_entry.runtime_data = runtime
    runtime.measure_point_cache["INV123"] = [
        MeasurePoint(key="SOC", name="Battery SOC", unit="%")
    ]

    devices = [
        Device(device_sn="INV123", device_type="INVERTER", station_id="101"),
        Device(device_sn="MTR456", device_type="METER", station_id="101"),
    ]
    await async_refresh_measure_point_cache(mock_config_entry, devices)

    mock_api_client.async_get_device_measure_points.assert_awaited_once_with("MTR456")
    assert "MTR456" in runtime.measure_point_cache


async def test_refresh_measure_point_cache_tolerates_partial_failure(
    hass, mock_config_entry, mock_api_client
) -> None:
    """One failed catalog fetch does not block caching for other devices."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator
    from custom_components.deyecloud.exceptions import DeyeCloudApiError

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    runtime = DeyeCloudRuntimeData(client=mock_api_client, coordinator=coordinator)
    mock_config_entry.runtime_data = runtime

    async def fetch_points(device_sn: str):
        if device_sn == "BAD999":
            raise DeyeCloudApiError("catalog failed")
        return [MeasurePoint(key="SOC", name="Battery SOC", unit="%")]

    mock_api_client.async_get_device_measure_points = AsyncMock(
        side_effect=fetch_points
    )

    devices = [
        Device(device_sn="BAD999", device_type="INVERTER", station_id="101"),
        Device(device_sn="GOOD888", device_type="METER", station_id="101"),
    ]
    await async_refresh_measure_point_cache(mock_config_entry, devices)

    assert "BAD999" not in runtime.measure_point_cache
    assert "GOOD888" in runtime.measure_point_cache


async def test_refresh_measure_point_cache_caches_permanent_failures(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Permanent measurePoints failures are cached as empty catalogs."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator
    from custom_components.deyecloud.exceptions import DeyeCloudApiError

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    runtime = DeyeCloudRuntimeData(client=mock_api_client, coordinator=coordinator)
    mock_config_entry.runtime_data = runtime

    mock_api_client.async_get_device_measure_points = AsyncMock(
        side_effect=DeyeCloudApiError("device not supported")
    )

    devices = [Device(device_sn="BAT001", device_type="BATTERY", station_id="101")]
    await async_refresh_measure_point_cache(mock_config_entry, devices)

    assert runtime.measure_point_cache["BAT001"] == []
    mock_api_client.async_get_device_measure_points.reset_mock()
    await async_refresh_measure_point_cache(mock_config_entry, devices)
    mock_api_client.async_get_device_measure_points.assert_not_awaited()


def test_iter_device_measure_specs_union() -> None:
    """Union includes catalog-only and latest-only keys."""
    station = StationCoordinatorData(
        info=Station(station_id="101", name="Home"),
        devices=[Device(device_sn="INV123", device_type="INVERTER", station_id="101")],
        device_data={
            "INV123": DeviceData(
                device_sn="INV123",
                device_type="INVERTER",
                device_state=1,
                data_list=[
                    DataPoint(key="TotalGridPower", value="1200", unit="W"),
                ],
            )
        },
        measure_points={
            "INV123": [
                MeasurePoint(key="SOC", name="Battery SOC", unit="%"),
                MeasurePoint(key="TotalGridPower", name="Grid", unit="W"),
            ]
        },
        station_latest=StationData(station_id="101", data={}),
    )

    specs = iter_device_measure_specs("INV123", station)
    keys = [key for key, _unit in specs]
    assert keys == ["SOC", "TotalGridPower"]


async def test_build_entities_from_catalog_only_key(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Sensors are created for catalog keys without latest values."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()

    station = coordinator.data["101"]
    station.measure_points["INV123"] = [
        MeasurePoint(key="FirmwareVersion", name="Firmware", unit=None),
        *station.measure_points.get("INV123", []),
    ]

    entities = _build_station_entities(coordinator, "101", station, "sub-101")
    firmware_entities = [
        entity for entity in entities if entity.unique_id.endswith("_firmware_version")
    ]
    assert firmware_entities
