"""Tests for binary sensor platform."""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er

from custom_components.deyecloud.binary_sensor import (
    DeyeCloudOnlineBinarySensor,
    _build_station_entities,
)
from custom_components.deyecloud.data import DeyeCloudRuntimeData
from tests.conftest import setup_config_entry


async def test_binary_sensor_is_on(hass, mock_config_entry, mock_api_client) -> None:
    """Binary sensor reflects device state."""
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
    assert isinstance(entities[0], DeyeCloudOnlineBinarySensor)
    assert entities[0].is_on is True


async def test_binary_sensor_setup(hass, mock_config_entry, mock_api_client) -> None:
    """Binary sensor platform sets up entities."""
    await setup_config_entry(hass, mock_config_entry)

    registry = er.async_get(hass)
    binary_entities = [
        entity
        for entity in registry.entities.values()
        if entity.config_entry_id == mock_config_entry.entry_id
        and entity.domain == "binary_sensor"
    ]
    assert binary_entities
