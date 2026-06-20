"""Tests for sensor platform."""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er

from custom_components.deyecloud.data import DeyeCloudRuntimeData
from custom_components.deyecloud.sensor import (
    DeyeCloudDeviceSensor,
    _build_station_entities,
    _iter_sensor_unique_ids,
)
from tests.conftest import setup_config_entry


async def test_build_station_entities(hass, mock_config_entry, mock_api_client) -> None:
    """Build device and plant sensors."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()
    plant_data = coordinator.data["101"]
    entities = _build_station_entities(coordinator, "101", plant_data, "sub-101")
    assert any(isinstance(entity, DeyeCloudDeviceSensor) for entity in entities)
    assert entities[0].unique_id.startswith("plant_101_")


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
