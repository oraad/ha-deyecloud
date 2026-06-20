"""Tests for the DeyeCloud coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.deyecloud.api_types import PlantCoordinatorData
from custom_components.deyecloud.const import CONF_SELECTED_PLANTS
from custom_components.deyecloud.coordinator import DeyeCloudCoordinator
from custom_components.deyecloud.data import DeyeCloudRuntimeData
from custom_components.deyecloud.exceptions import (
    DeyeCloudAuthError,
    DeyeCloudConnectionError,
)


async def test_coordinator_update(hass, mock_config_entry, mock_api_client) -> None:
    """Coordinator returns plant keyed data."""
    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )

    await coordinator.async_refresh()
    await hass.async_block_till_done()
    data = coordinator.data
    assert data is not None
    assert "101" in data
    assert isinstance(data["101"], PlantCoordinatorData)
    assert data["101"].devices[0].device_sn == "INV123"
    mock_api_client.async_get_device_measure_points.assert_not_called()


async def test_coordinator_respects_selected_plants(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Coordinator only loads selected plants."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={CONF_SELECTED_PLANTS: ["999"]},
    )
    entry = hass.config_entries.async_get_entry(mock_config_entry.entry_id)
    assert entry is not None
    coordinator = DeyeCloudCoordinator(hass, entry)
    entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )

    await coordinator.async_refresh()
    assert coordinator.data == {}


async def test_coordinator_auth_failed(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Coordinator raises ConfigEntryAuthFailed on auth errors."""
    mock_config_entry.add_to_hass(hass)
    mock_api_client.async_get_stations = AsyncMock(side_effect=DeyeCloudAuthError())
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_connection_failed(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Coordinator raises UpdateFailed on connection errors."""
    mock_config_entry.add_to_hass(hass)
    mock_api_client.async_get_stations = AsyncMock(
        side_effect=DeyeCloudConnectionError()
    )
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
