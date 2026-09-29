"""Tests for the DeyeCloud coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.deyecloud.api_types import (
    Device,
    Station,
    StationCoordinatorData,
    StationData,
)
from custom_components.deyecloud.const import CONF_SELECTED_STATIONS
from custom_components.deyecloud.coordinator import DeyeCloudCoordinator
from custom_components.deyecloud.data import DeyeCloudRuntimeData
from custom_components.deyecloud.exceptions import (
    DeyeCloudAuthError,
    DeyeCloudConnectionError,
)


async def test_coordinator_update(hass, mock_config_entry, mock_api_client) -> None:
    """Coordinator returns station keyed data."""
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
    assert isinstance(data["101"], StationCoordinatorData)
    assert data["101"].devices[0].device_sn == "INV123"
    mock_api_client.async_get_device_measure_points.assert_not_called()


async def test_coordinator_respects_selected_stations(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Coordinator only loads selected stations."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={CONF_SELECTED_STATIONS: ["999"]},
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
        await _refresh(coordinator)


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
        await _refresh(coordinator)


def _optimizer_station() -> Station:
    return Station(
        station_id="101",
        name="Home Plant",
        raw={"regionTimezone": "Asia/Kolkata"},
    )


def _optimizer_device(device_type: str = "OPTIMIZER", connect: int = 1) -> Device:
    return Device(
        device_sn="OPT123",
        device_type=device_type,
        station_id="101",
        connect_status=connect,
    )


def _coordinator_with_devices(hass, mock_config_entry, mock_api_client, devices):
    mock_config_entry.add_to_hass(hass)
    mock_api_client.async_get_stations = AsyncMock(return_value=[_optimizer_station()])
    mock_api_client.async_get_station_devices = AsyncMock(return_value=devices)
    mock_api_client.async_get_device_latest = AsyncMock(return_value=[])
    mock_api_client.async_get_station_latest = AsyncMock(
        return_value=StationData(station_id="101", data={})
    )
    mock_api_client.async_get_device_history = AsyncMock(
        return_value=[
            {
                "time": "2026-09-28",
                "itemList": [{"key": "Production", "value": "0.42"}],
            }
        ]
    )
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    return coordinator


async def _refresh(coordinator: DeyeCloudCoordinator):
    """
    Run one update the way DataUpdateCoordinator does, assigning self.data.

    ``_async_update_data`` reuses the previous payload for throttled optimizer
    records, so a test that calls it directly must publish the result the way
    ``_async_refresh`` would.
    """
    coordinator.data = await coordinator._async_update_data()
    return coordinator.data


async def test_coordinator_excludes_optimizers_from_latest(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Telemetry-less devices never reach /device/latest."""
    devices = [
        Device(device_sn="INV123", device_type="INVERTER", station_id="101"),
        _optimizer_device(),
        _optimizer_device("OPTIMIZER_CONCENTRATOR"),
        Device(device_sn="LOG1", device_type="COLLECTOR", station_id="101"),
        Device(device_sn="MTR456", device_type="METER", station_id="101"),
    ]
    coordinator = _coordinator_with_devices(
        hass, mock_config_entry, mock_api_client, devices
    )

    await _refresh(coordinator)

    sent = mock_api_client.async_get_device_latest.call_args[0][0]
    assert sent == ["INV123", "MTR456"]


async def test_coordinator_keeps_unknown_device_types_in_latest(
    hass, mock_config_entry, mock_api_client
) -> None:
    """An unrecognised deviceType is still polled rather than silently dropped."""
    devices = [
        Device(device_sn="NEW1", device_type="SOME_FUTURE_TYPE", station_id="101"),
        Device(device_sn="NOTYPE", device_type=None, station_id="101"),
    ]
    coordinator = _coordinator_with_devices(
        hass, mock_config_entry, mock_api_client, devices
    )

    await _refresh(coordinator)

    sent = mock_api_client.async_get_device_latest.call_args[0][0]
    assert sent == ["NEW1", "NOTYPE"]


async def test_coordinator_fetches_optimizer_history(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Optimizers pull daily Production from /device/history."""
    coordinator = _coordinator_with_devices(
        hass, mock_config_entry, mock_api_client, [_optimizer_device()]
    )

    data = await _refresh(coordinator)

    kwargs = mock_api_client.async_get_device_history.call_args[1]
    assert kwargs["granularity"] == 2
    assert kwargs["end_at"] >= kwargs["start_at"]
    record = data["101"].optimizers["OPT123"]
    assert record.today == 0.42
    # The first sample of the day can only seed the window.
    assert record.power is None


async def test_coordinator_skips_concentrator_history(
    hass, mock_config_entry, mock_api_client
) -> None:
    """The concentrator carries no per-panel series and is not polled."""
    coordinator = _coordinator_with_devices(
        hass,
        mock_config_entry,
        mock_api_client,
        [_optimizer_device("OPTIMIZER_CONCENTRATOR")],
    )

    data = await _refresh(coordinator)

    mock_api_client.async_get_device_history.assert_not_called()
    assert data["101"].optimizers == {}


async def test_coordinator_throttles_optimizer_history(
    hass, mock_config_entry, mock_api_client
) -> None:
    """A second poll inside the 15 minute window reuses the previous records."""
    coordinator = _coordinator_with_devices(
        hass, mock_config_entry, mock_api_client, [_optimizer_device()]
    )

    await _refresh(coordinator)
    mock_api_client.async_get_device_history.reset_mock()
    data = await _refresh(coordinator)

    mock_api_client.async_get_device_history.assert_not_called()
    assert data["101"].optimizers["OPT123"].today == 0.42


async def test_coordinator_refetches_after_interval(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Once the interval elapses the history poll runs again."""
    coordinator = _coordinator_with_devices(
        hass, mock_config_entry, mock_api_client, [_optimizer_device()]
    )

    await _refresh(coordinator)
    # Pretend the throttling window has long since elapsed.
    mock_config_entry.runtime_data.optimizer_last_poll = 0.0
    mock_api_client.async_get_device_history.reset_mock()
    await _refresh(coordinator)

    assert mock_api_client.async_get_device_history.call_count == 1


async def test_coordinator_keeps_last_record_on_history_failure(
    hass, mock_config_entry, mock_api_client
) -> None:
    """A failed history call must not wipe the last good optimizer values."""
    coordinator = _coordinator_with_devices(
        hass, mock_config_entry, mock_api_client, [_optimizer_device()]
    )

    await _refresh(coordinator)
    mock_api_client.async_get_device_history = AsyncMock(
        side_effect=DeyeCloudConnectionError("boom")
    )
    mock_config_entry.runtime_data.optimizer_last_poll = 1.0
    data = await _refresh(coordinator)

    assert data["101"].optimizers["OPT123"].today == 0.42


async def test_coordinator_drops_state_for_removed_optimizer(
    hass, mock_config_entry, mock_api_client
) -> None:
    """The open power window is discarded once the optimizer leaves the plant."""
    coordinator = _coordinator_with_devices(
        hass, mock_config_entry, mock_api_client, [_optimizer_device()]
    )

    await _refresh(coordinator)
    assert "OPT123" in mock_config_entry.runtime_data.optimizer_state

    mock_api_client.async_get_station_devices = AsyncMock(
        return_value=[
            Device(device_sn="INV123", device_type="INVERTER", station_id="101")
        ]
    )
    await _refresh(coordinator)

    assert "OPT123" not in mock_config_entry.runtime_data.optimizer_state
    assert "101" in coordinator.data


async def test_coordinator_marks_offline_optimizer_zero_power(
    hass, mock_config_entry, mock_api_client
) -> None:
    """ConnectStatus 0 reports zero watts rather than a stale average."""
    coordinator = _coordinator_with_devices(
        hass, mock_config_entry, mock_api_client, [_optimizer_device(connect=0)]
    )

    data = await _refresh(coordinator)

    record = data["101"].optimizers["OPT123"]
    assert record.online is False
    assert record.power == 0.0
