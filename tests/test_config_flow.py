"""Tests for DeyeCloud config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.deyecloud.api_types import Station
from custom_components.deyecloud.config_flow import (
    DeyeCloudConfigFlow,
    PlantSubentryFlowHandler,
)
from custom_components.deyecloud.const import (
    CONF_APP_ID,
    CONF_APP_SECRET,
    CONF_BASE_URL,
    CONF_SELECTED_PLANTS,
    CONF_USERNAME,
    DEFAULT_BASE_URL_EU,
    DOMAIN,
)
from custom_components.deyecloud.exceptions import (
    DeyeCloudAuthError,
    DeyeCloudConnectionError,
    DeyeCloudNoStationsError,
)

FLOW_STATIONS = [
    Station(station_id="101", name="Home Plant"),
    Station(station_id="202", name="Office Plant"),
]

USER_INPUT = {
    CONF_USERNAME: "user@example.com",
    CONF_PASSWORD: "secret",
    CONF_APP_ID: "app-id",
    CONF_APP_SECRET: "app-secret",
    CONF_BASE_URL: DEFAULT_BASE_URL_EU,
}


async def test_user_flow_success(hass) -> None:
    """Test successful user flow with plant selection."""
    with patch(
        "custom_components.deyecloud.config_flow._async_validate_account",
        AsyncMock(return_value=FLOW_STATIONS),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "plant_select"

    with patch(
        "custom_components.deyecloud.config_flow._async_validate_account",
        AsyncMock(return_value=FLOW_STATIONS),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_SELECTED_PLANTS: ["101"]},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "DeyeCloud - user@example.com"
    assert result["options"][CONF_SELECTED_PLANTS] == ["101"]


async def test_user_flow_single_plant_auto_select(hass) -> None:
    """Test user flow skips selection when only one plant exists."""
    with patch(
        "custom_components.deyecloud.config_flow._async_validate_account",
        AsyncMock(return_value=[FLOW_STATIONS[0]]),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_SELECTED_PLANTS] == ["101"]


async def test_user_flow_auth_failed(hass) -> None:
    """Test auth failure."""
    with patch(
        "custom_components.deyecloud.config_flow._async_validate_account",
        AsyncMock(side_effect=DeyeCloudAuthError()),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "auth_failed"}


async def test_user_flow_no_stations(hass) -> None:
    """Test no stations error."""
    with patch(
        "custom_components.deyecloud.config_flow._async_validate_account",
        AsyncMock(side_effect=DeyeCloudNoStationsError()),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["errors"] == {"base": "no_stations_found"}


async def test_user_flow_cannot_connect(hass) -> None:
    """Test connection failure."""
    with patch(
        "custom_components.deyecloud.config_flow._async_validate_account",
        AsyncMock(side_effect=DeyeCloudConnectionError()),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_unique_id(hass) -> None:
    """Test duplicate entry abort."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_APP_ID: "app-id",
            CONF_APP_SECRET: "app-secret",
            CONF_BASE_URL: DEFAULT_BASE_URL_EU,
        },
        unique_id="user@example.com:personal",
    )
    existing.add_to_hass(hass)

    with patch(
        "custom_components.deyecloud.config_flow._async_validate_account",
        AsyncMock(return_value=FLOW_STATIONS),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(hass, mock_config_entry) -> None:
    """Test reauth flow."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.deyecloud.config_flow._async_validate_account",
        AsyncMock(return_value=FLOW_STATIONS),
    ):
        result = await mock_config_entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "user@example.com",
                CONF_PASSWORD: "new-secret",
                CONF_APP_ID: "app-id",
                CONF_APP_SECRET: "app-secret",
                CONF_BASE_URL: DEFAULT_BASE_URL_EU,
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reconfigure_flow(hass, mock_config_entry) -> None:
    """Test reconfigure flow."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.deyecloud.config_flow._async_validate_account",
        AsyncMock(return_value=FLOW_STATIONS),
    ):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "user@example.com",
                CONF_PASSWORD: "new-secret",
                CONF_APP_ID: "app-id",
                CONF_APP_SECRET: "app-secret",
                CONF_BASE_URL: DEFAULT_BASE_URL_EU,
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_options_credentials(hass, mock_config_entry) -> None:
    """Test options credentials update."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.deyecloud.config_flow._async_validate_account",
        AsyncMock(return_value=FLOW_STATIONS),
    ):
        result = await hass.config_entries.options.async_init(
            mock_config_entry.entry_id
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"next_step_id": "credentials"},
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "user@example.com",
                CONF_PASSWORD: "new-secret",
                CONF_APP_ID: "app-id",
                CONF_APP_SECRET: "app-secret",
                CONF_BASE_URL: DEFAULT_BASE_URL_EU,
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_options_plants(hass, mock_config_entry) -> None:
    """Test options flow plant selection."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.deyecloud.config_flow._async_fetch_stations",
        AsyncMock(return_value=FLOW_STATIONS),
    ):
        result = await hass.config_entries.options.async_init(
            mock_config_entry.entry_id
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"next_step_id": "plants"},
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={CONF_SELECTED_PLANTS: ["202"]},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = hass.config_entries.async_get_entry(mock_config_entry.entry_id)
    assert entry is not None
    assert entry.options[CONF_SELECTED_PLANTS] == ["202"]


async def test_supported_subentry_types(hass, mock_config_entry) -> None:
    """Test plant subentry type is always exposed."""
    assert DeyeCloudConfigFlow.async_get_supported_subentry_types(
        mock_config_entry
    ) == {"plant": PlantSubentryFlowHandler}
