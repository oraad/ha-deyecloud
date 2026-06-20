"""Test fixtures for DeyeCloud."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.deyecloud.api_types import (
    DataPoint,
    Device,
    DeviceData,
    MeasurePoint,
    Station,
    StationData,
)
from custom_components.deyecloud.const import (
    CONF_APP_ID,
    CONF_APP_SECRET,
    CONF_BASE_URL,
    CONF_PASSWORD,
    CONF_SELECTED_STATIONS,
    CONF_USERNAME,
    DEFAULT_BASE_URL_EU,
    DOMAIN,
)

FIXTURES = Path(__file__).parent / "fixtures"

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom integrations from custom_components for every test."""


MIN_HA_VERSION = (2026, 3, 0)


def _parse_ha_version(version: str) -> tuple[int, int, int]:
    """Parse a Home Assistant version string into (major, minor, patch)."""
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        pytest.fail(f"Unrecognized Home Assistant version: {version!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def pytest_configure(config: pytest.Config) -> None:
    """Fail fast when the test environment uses an unsupported HA release."""
    try:
        from homeassistant.const import __version__ as ha_version
    except ImportError:
        return

    if _parse_ha_version(ha_version) < MIN_HA_VERSION:
        pytest.exit(
            f"Home Assistant {ha_version} is not supported; require >= 2026.3.0",
            returncode=1,
        )


def load_fixture(name: str) -> dict[str, Any]:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def config_data() -> dict[str, str]:
    """Return valid config entry data."""
    return {
        CONF_USERNAME: "user@example.com",
        CONF_PASSWORD: "secret",
        CONF_APP_ID: "app-id",
        CONF_APP_SECRET: "app-secret",
        CONF_BASE_URL: DEFAULT_BASE_URL_EU,
    }


@pytest.fixture
def mock_config_entry(config_data: dict[str, str]):
    """Return a mock config entry when Home Assistant test libs are available."""
    pytest.importorskip("homeassistant")
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    return MockConfigEntry(
        domain=DOMAIN,
        data=config_data,
        options={CONF_SELECTED_STATIONS: ["101"]},
        title="DeyeCloud - user@example.com",
        unique_id="user@example.com:personal",
        version=2,
    )


@pytest.fixture
def mock_api_client():
    """Patch DeyeCloudApiClient with an AsyncMock."""
    with patch(
        "custom_components.deyecloud.api.DeyeCloudApiClient",
        autospec=True,
    ) as mock_cls:
        client = mock_cls.return_value
        client.access_token = "token"
        client.async_authenticate = AsyncMock()
        client.async_get_stations = AsyncMock(
            return_value=[
                Station(station_id="101", name="Home Plant"),
                Station(station_id="202", name="Office Plant"),
            ]
        )
        client.async_get_station_devices = AsyncMock(
            return_value=[
                Device(
                    device_sn="INV123",
                    device_type="INVERTER",
                    station_id="101",
                    device_state=1,
                    connect_status=1,
                ),
                Device(
                    device_sn="MTR456",
                    device_type="METER",
                    station_id="101",
                    device_state=1,
                    connect_status=1,
                ),
            ]
        )
        client.async_get_device_measure_points = AsyncMock(
            return_value=[
                MeasurePoint(key="SOC", name="Battery SOC", unit="%"),
                MeasurePoint(key="TotalGridPower", name="Total Grid Power", unit="W"),
            ]
        )
        client.async_get_device_latest = AsyncMock(
            return_value=[
                DeviceData(
                    device_sn="INV123",
                    device_type="INVERTER",
                    device_state=1,
                    data_list=[
                        DataPoint(key="SOC", value="85", unit="%", name="Battery SOC"),
                        DataPoint(
                            key="TotalGridPower",
                            value="1200",
                            unit="W",
                            name="Total Grid Power",
                        ),
                    ],
                )
            ]
        )
        client.async_get_station_latest = AsyncMock(
            return_value=StationData(
                station_id="101",
                data={
                    "generationPower": 12.5,
                    "consumptionPower": 8.2,
                    "gridPower": 3.1,
                    "batterySOC": 85.0,
                },
            )
        )
        yield client


async def setup_config_entry(hass, mock_config_entry) -> None:
    """Set up the integration through the config entry manager."""
    from unittest.mock import AsyncMock, patch

    from homeassistant.config_entries import ConfigSubentry

    from custom_components.deyecloud.const import CONF_STATION_ID, SUBENTRY_TYPE_STATION
    from custom_components.deyecloud.subentry_sync import build_station_subentry_map

    async def _sync_subentries(hass, entry, stations):
        current = hass.config_entries.async_get_entry(entry.entry_id)
        if current is None:
            return {}, False, False
        if not current.subentries:
            hass.config_entries.async_add_subentry(
                current,
                ConfigSubentry(
                    data={CONF_STATION_ID: "101"},
                    subentry_type=SUBENTRY_TYPE_STATION,
                    title="Home Plant",
                    unique_id="101",
                ),
            )
            current = hass.config_entries.async_get_entry(entry.entry_id)
        if current is None:
            return {}, False, False
        return build_station_subentry_map(current), False, False

    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.deyecloud.subentry_sync.async_sync_station_subentries",
        AsyncMock(side_effect=_sync_subentries),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
