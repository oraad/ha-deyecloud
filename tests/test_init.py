"""Tests for integration setup."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.deyecloud import PLATFORMS
from custom_components.deyecloud.const import (
    DOMAIN,
    ISSUE_API_UNAVAILABLE,
    ISSUE_AUTH_FAILED,
    STALE_DEVICE_MISSING_POLLS,
)
from tests.conftest import setup_config_entry


async def test_first_install_creates_entities_without_reload(
    hass, mock_config_entry, mock_api_client
) -> None:
    """First setup creates subentries and entities without scheduling reload."""
    mock_config_entry.add_to_hass(hass)

    with patch.object(
        hass.config_entries,
        "async_schedule_reload",
    ) as schedule_reload:
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)

    await hass.async_block_till_done()
    schedule_reload.assert_not_called()

    entry = hass.config_entries.async_get_entry(mock_config_entry.entry_id)
    assert entry is not None
    assert entry.state is ConfigEntryState.LOADED
    assert entry.subentries

    registry = er.async_get(hass)
    entities = [
        entity
        for entity in registry.entities.values()
        if entity.config_entry_id == mock_config_entry.entry_id
    ]
    assert entities


async def test_setup_schedules_reload_when_subentries_change(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Runtime structural subentry changes schedule a reload."""
    from homeassistant.config_entries import ConfigSubentry
    from types import MappingProxyType

    from custom_components.deyecloud.const import CONF_STATION_ID, SUBENTRY_TYPE_PLANT

    mock_config_entry.add_to_hass(hass)
    entry = hass.config_entries.async_get_entry(mock_config_entry.entry_id)
    assert entry is not None
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data=MappingProxyType({CONF_STATION_ID: "999"}),
            subentry_type=SUBENTRY_TYPE_PLANT,
            title="Stale Plant",
            unique_id="999",
        ),
    )

    with patch.object(
        hass.config_entries,
        "async_schedule_reload",
    ) as schedule_reload:
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)

    schedule_reload.assert_called_once_with(mock_config_entry.entry_id)


async def test_setup_and_unload(hass, mock_config_entry, mock_api_client) -> None:
    """Test setup creates entities and unloads cleanly."""
    await setup_config_entry(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data.coordinator is not None

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    entry = hass.config_entries.async_get_entry(mock_config_entry.entry_id)
    assert entry is not None
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_auth_failed_creates_issue(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Test auth failure creates repair issue."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.deyecloud.coordinator.DeyeCloudCoordinator.async_config_entry_first_refresh",
        AsyncMock(side_effect=ConfigEntryAuthFailed("auth")),
    ):
        from custom_components.deyecloud import async_setup_entry

        try:
            await async_setup_entry(hass, mock_config_entry)
        except ConfigEntryAuthFailed:
            pass

    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_AUTH_FAILED)
    assert issue is not None


async def test_setup_api_unavailable_creates_issue(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Test API failure creates repair issue."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.deyecloud.coordinator.DeyeCloudCoordinator.async_config_entry_first_refresh",
        AsyncMock(side_effect=UpdateFailed("offline")),
    ):
        from custom_components.deyecloud import async_setup_entry

        try:
            await async_setup_entry(hass, mock_config_entry)
        except UpdateFailed:
            pass

    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_API_UNAVAILABLE)
    assert issue is not None


async def test_coordinator_listener_discovers_new_sensor(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Runtime discovery adds sensors when coordinator data expands."""
    from custom_components.deyecloud.api_types import (
        DataPoint,
        DeviceData,
        MeasurePoint,
    )

    await setup_config_entry(hass, mock_config_entry)

    runtime = mock_config_entry.runtime_data
    plant = runtime.coordinator.data["101"]
    plant.device_data["INV123"] = DeviceData(
        device_sn="INV123",
        device_type="INVERTER",
        device_state=1,
        data_list=[
            *plant.device_data["INV123"].data_list,
            DataPoint(key="BatteryPower", value="500", unit="W"),
        ],
    )
    plant.measure_points["INV123"] = [
        *plant.measure_points.get("INV123", []),
        MeasurePoint(key="BatteryPower", name="Battery power", unit="W"),
    ]

    from custom_components.deyecloud import _async_coordinator_listener

    await _async_coordinator_listener(hass, mock_config_entry)
    await hass.async_block_till_done()

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    assert any(
        entity.unique_id and entity.unique_id.endswith("_battery_power")
        for entity in registry.entities.values()
        if entity.config_entry_id == mock_config_entry.entry_id
    )


async def test_platforms_list() -> None:
    """Test expected platforms are registered."""
    from homeassistant.const import Platform

    assert Platform.SENSOR in PLATFORMS
    assert Platform.BINARY_SENSOR in PLATFORMS


async def test_listener_queues_trailing_pass_when_polls_overlap(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Overlapping listener calls schedule a trailing maintenance pass."""
    from custom_components.deyecloud import _async_coordinator_listener

    await setup_config_entry(hass, mock_config_entry)
    runtime = mock_config_entry.runtime_data
    call_count = 0

    async def slow_sync(*args: object, **kwargs: object) -> tuple[dict, bool, bool]:
        nonlocal call_count
        call_count += 1
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

    assert call_count >= 2


async def test_listener_removes_stale_when_coordinator_data_empty(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Stale entity removal runs even when coordinator data is empty."""
    from custom_components.deyecloud import _async_coordinator_listener

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

    runtime.coordinator.data = {}
    for _ in range(STALE_DEVICE_MISSING_POLLS):
        await _async_coordinator_listener(hass, mock_config_entry)

    inv_entities_after = [
        entity
        for entity in registry.entities.values()
        if entity.config_entry_id == mock_config_entry.entry_id
        and entity.unique_id
        and "INV123" in entity.unique_id
    ]
    assert not inv_entities_after
