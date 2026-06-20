"""Tests for sensor platform."""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er

from custom_components.deyecloud.data import DeyeCloudRuntimeData
from custom_components.deyecloud.sensor import (
    DeyeCloudDeviceSensor,
    DeyeCloudStationSensor,
    DeyeCloudStationStatusSensor,
    _build_station_entities,
    _iter_sensor_unique_ids,
)
from tests.conftest import setup_config_entry


async def test_build_station_entities(hass, mock_config_entry, mock_api_client) -> None:
    """Build device and station sensors."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()
    station_data = coordinator.data["101"]
    entities = _build_station_entities(coordinator, "101", station_data, "sub-101")
    assert any(isinstance(entity, DeyeCloudDeviceSensor) for entity in entities)
    assert any(isinstance(entity, DeyeCloudStationSensor) for entity in entities)
    assert entities[0].unique_id.startswith("station_101_")


async def test_build_station_entities_uses_generation_power(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Station sensors are created from production station/latest keys."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()
    station_data = coordinator.data["101"]
    entities = _build_station_entities(coordinator, "101", station_data, "sub-101")
    station_entities = [
        entity for entity in entities if isinstance(entity, DeyeCloudStationSensor)
    ]
    assert any(
        entity.unique_id == "station_101_station_generation_power"
        for entity in station_entities
    )
    assert any(
        entity.unique_id == "station_101_station_battery_soc"
        for entity in station_entities
    )


async def test_build_station_entities_adds_station_status_fallback(
    hass, mock_config_entry, mock_api_client
) -> None:
    """A station status sensor is created when station metrics are unavailable."""
    from custom_components.deyecloud.api_types import (
        Station,
        StationCoordinatorData,
        StationData,
    )
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()
    station_data = StationCoordinatorData(
        info=Station(station_id="101", name="Home Plant"),
        devices=coordinator.data["101"].devices,
        device_data=coordinator.data["101"].device_data,
        measure_points=coordinator.data["101"].measure_points,
        station_latest=StationData(station_id="101", data={"unexpectedField": 1}),
    )
    entities = _build_station_entities(coordinator, "101", station_data, "sub-101")
    assert any(isinstance(entity, DeyeCloudStationStatusSensor) for entity in entities)


async def test_build_station_entities_without_station_latest(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Station status sensor is created when station latest data is missing."""
    from custom_components.deyecloud.api_types import Station, StationCoordinatorData
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()
    station_data = StationCoordinatorData(
        info=Station(station_id="101", name="Home Plant"),
        devices=coordinator.data["101"].devices,
        device_data=coordinator.data["101"].device_data,
        measure_points=coordinator.data["101"].measure_points,
        station_latest=None,
    )
    entities = _build_station_entities(coordinator, "101", station_data, "sub-101")
    status_entities = [
        entity
        for entity in entities
        if isinstance(entity, DeyeCloudStationStatusSensor)
    ]
    assert len(status_entities) == 1
    assert status_entities[0].native_value == "ok"


async def test_iter_sensor_unique_ids(hass, mock_config_entry, mock_api_client) -> None:
    """Collect unique ids from coordinator data."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()
    unique_ids = _iter_sensor_unique_ids(coordinator.data)
    assert any("dev_INV123" in unique_id for unique_id in unique_ids)


async def test_sensor_setup(hass, mock_config_entry, mock_api_client) -> None:
    """Sensor platform sets up entities."""
    await setup_config_entry(hass, mock_config_entry)

    registry = er.async_get(hass)
    sensor_entities = [
        entity
        for entity in registry.entities.values()
        if entity.config_entry_id == mock_config_entry.entry_id
        and entity.domain == "sensor"
    ]
    assert sensor_entities
