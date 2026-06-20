"""Tests for entity helpers and runtime discovery."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from custom_components.deyecloud.api_types import Device
from custom_components.deyecloud.const import device_type_label
from custom_components.deyecloud.discovery import async_discover_all_entities
from tests.conftest import setup_config_entry


def test_device_type_label() -> None:
    """Return friendly labels for known and unknown device types."""
    assert device_type_label("INVERTER") == "Inverter"
    assert device_type_label(None) == "Device"
    assert device_type_label("CUSTOM_TYPE") == "Custom Type"


async def test_binary_sensor_runtime_discovery(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Runtime discovery adds online binary sensors for new devices."""
    await setup_config_entry(hass, mock_config_entry)
    runtime = mock_config_entry.runtime_data
    plant = runtime.coordinator.data["101"]
    plant.devices.append(
        Device(
            device_sn="NEW789",
            device_type="METER",
            station_id="101",
            device_state=1,
            connect_status=1,
        )
    )

    await async_discover_all_entities(hass, mock_config_entry)
    await hass.async_block_till_done()

    assert any(
        unique_id.endswith("_online") and "NEW789" in unique_id
        for unique_id in runtime.known_binary_unique_ids
    )


async def test_unified_discovery_skips_when_in_progress(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Unified discovery is skipped while another pass is running."""
    await setup_config_entry(hass, mock_config_entry)
    runtime = mock_config_entry.runtime_data
    before = set(runtime.known_sensor_unique_ids)
    runtime.discovery_in_progress = True

    await async_discover_all_entities(hass, mock_config_entry)
    assert runtime.known_sensor_unique_ids == before

    runtime.discovery_in_progress = False


async def test_coordinator_listener_sets_pending_when_lock_held(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Coordinator listener queues a trailing pass when the lock is held."""
    from custom_components.deyecloud import _async_coordinator_listener

    await setup_config_entry(hass, mock_config_entry)
    runtime = mock_config_entry.runtime_data

    async def slow_sync(*args: object, **kwargs: object) -> tuple[dict, bool, bool]:
        await asyncio.sleep(0.05)
        return {}, False, False

    with patch(
        "custom_components.deyecloud.subentry_sync.async_sync_plant_subentries",
        side_effect=slow_sync,
    ):
        first = asyncio.create_task(
            _async_coordinator_listener(hass, mock_config_entry)
        )
        await asyncio.sleep(0.01)
        await _async_coordinator_listener(hass, mock_config_entry)
        assert runtime.listener_pending is True
        await first

    runtime.discovery_in_progress = False
