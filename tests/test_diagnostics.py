"""Tests for diagnostics."""

from __future__ import annotations

from custom_components.deyecloud.const import CONF_APP_SECRET, CONF_PASSWORD
from custom_components.deyecloud.diagnostics import async_get_config_entry_diagnostics
from tests.conftest import setup_config_entry


async def test_diagnostics_redacts_secrets(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Diagnostics redact sensitive fields."""
    await setup_config_entry(hass, mock_config_entry)

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert result["entry"]["data"][CONF_PASSWORD] == "**REDACTED**"
    assert result["entry"]["data"][CONF_APP_SECRET] == "**REDACTED**"
    assert result["client"]["has_token"] is True
