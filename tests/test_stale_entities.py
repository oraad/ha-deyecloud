"""Tests for stale entity removal."""

from __future__ import annotations

from custom_components.deyecloud.const import STALE_DEVICE_MISSING_POLLS
from custom_components.deyecloud.stale_entities import (
    _device_sn_from_unique_id,
    async_remove_stale_entities,
)
from tests.conftest import setup_config_entry


def test_device_sn_from_unique_id() -> None:
    """Parse device serial numbers from entity unique ids."""
    assert _device_sn_from_unique_id("station_101_dev_INV123_soc", "sensor") == "INV123"
    assert (
        _device_sn_from_unique_id("station_101_dev_INV123_online", "binary_sensor")
        == "INV123"
    )
    assert _device_sn_from_unique_id("station_101_station_generation", "sensor") is None


async def test_stale_removal_after_three_polls(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Missing devices are removed after exactly three coordinator polls."""
    from homeassistant.helpers import entity_registry as er

    await setup_config_entry(hass, mock_config_entry)

    runtime = mock_config_entry.runtime_data
    registry = er.async_get(hass)
    inv_entities_before = [
        entity
        for entity in registry.entities.values()
        if entity.config_entry_id == mock_config_entry.entry_id
        and entity.unique_id
        and "INV123" in entity.unique_id
    ]
    assert inv_entities_before

    runtime.coordinator.data["101"].devices = []

    for poll in range(1, STALE_DEVICE_MISSING_POLLS):
        await async_remove_stale_entities(hass, mock_config_entry)
        assert runtime.missing_device_polls.get("INV123") == poll
        assert [
            entity
            for entity in registry.entities.values()
            if entity.config_entry_id == mock_config_entry.entry_id
            and entity.unique_id
            and "INV123" in entity.unique_id
        ]

    await async_remove_stale_entities(hass, mock_config_entry)
    inv_entities_after = [
        entity
        for entity in registry.entities.values()
        if entity.config_entry_id == mock_config_entry.entry_id
        and entity.unique_id
        and "INV123" in entity.unique_id
    ]
    assert not inv_entities_after
