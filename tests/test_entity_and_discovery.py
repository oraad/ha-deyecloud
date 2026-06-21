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
    assert device_type_label("COLLECTOR") == "Collector"
    assert device_type_label(None) == "Device"
    assert device_type_label("CUSTOM_TYPE") == "Custom Type"


async def test_binary_sensor_runtime_discovery(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Runtime discovery adds online binary sensors for new devices."""
    await setup_config_entry(hass, mock_config_entry)
    runtime = mock_config_entry.runtime_data
    station = runtime.coordinator.data["101"]
    station.devices.append(
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
        "custom_components.deyecloud.subentry_sync.async_sync_station_subentries",
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


async def test_child_device_name_type_only(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Single device type uses label-only DeviceInfo name."""
    from custom_components.deyecloud.binary_sensor import DeyeCloudOnlineBinarySensor
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator
    from custom_components.deyecloud.data import DeyeCloudRuntimeData

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()

    entity = DeyeCloudOnlineBinarySensor(
        coordinator,
        station_id="101",
        subentry_id="sub-101",
        device=coordinator.data["101"].devices[0],
    )
    assert entity.device_info is not None
    assert entity.device_info.get("name") == "Inverter"
    assert entity.device_info.get("serial_number") == "INV123"


async def test_child_device_name_appends_sn_for_duplicate_types(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Duplicate device types append serial to DeviceInfo name."""
    from custom_components.deyecloud.api_types import Device, StationCoordinatorData
    from custom_components.deyecloud.binary_sensor import DeyeCloudOnlineBinarySensor
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator
    from custom_components.deyecloud.data import DeyeCloudRuntimeData

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()

    station_data = coordinator.data["101"]
    station_data.devices.append(
        Device(
            device_sn="BAT002",
            device_type="BATTERY",
            station_id="101",
            device_state=1,
            connect_status=1,
        )
    )
    station_data.devices.append(
        Device(
            device_sn="BAT003",
            device_type="BATTERY",
            station_id="101",
            device_state=1,
            connect_status=1,
        )
    )
    coordinator.data["101"] = StationCoordinatorData(
        info=station_data.info,
        devices=station_data.devices,
        device_data=station_data.device_data,
        measure_points=station_data.measure_points,
        station_latest=station_data.station_latest,
    )

    bat002 = DeyeCloudOnlineBinarySensor(
        coordinator,
        station_id="101",
        subentry_id="sub-101",
        device=station_data.devices[-2],
    )
    bat003 = DeyeCloudOnlineBinarySensor(
        coordinator,
        station_id="101",
        subentry_id="sub-101",
        device=station_data.devices[-1],
    )
    assert bat002.device_info is not None
    assert bat003.device_info is not None
    assert bat002.device_info.get("name") == "Battery BAT002"
    assert bat003.device_info.get("name") == "Battery BAT003"


async def test_station_hub_device_model(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Station hub device uses Station model label."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator
    from custom_components.deyecloud.data import DeyeCloudRuntimeData
    from custom_components.deyecloud.sensor import DeyeCloudStationSensor

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()

    entity = DeyeCloudStationSensor(
        coordinator,
        station_id="101",
        subentry_id="sub-101",
        metric_key="generationPower",
    )
    assert entity.device_info is not None
    assert entity.device_info.get("model") == "Station"
    assert entity.device_info.get("name") == "Home Plant"


async def test_child_device_name_without_station_data(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Device name falls back to label when station data is unavailable."""
    from custom_components.deyecloud.api_types import Device
    from custom_components.deyecloud.binary_sensor import DeyeCloudOnlineBinarySensor
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator
    from custom_components.deyecloud.data import DeyeCloudRuntimeData

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    coordinator.data = {}

    entity = DeyeCloudOnlineBinarySensor(
        coordinator,
        station_id="101",
        subentry_id="sub-101",
        device=Device(
            device_sn="INV123",
            device_type="INVERTER",
            station_id="101",
        ),
    )
    assert entity.device_info is not None
    assert entity.device_info.get("name") == "Inverter"
