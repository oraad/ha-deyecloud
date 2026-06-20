"""Tests for unified runtime discovery."""

from __future__ import annotations

from custom_components.deyecloud.discovery import async_discover_all_entities
from tests.conftest import setup_config_entry


async def test_discover_all_entities_skips_when_in_progress(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Unified discovery is skipped while a pass is already running."""
    await setup_config_entry(hass, mock_config_entry)
    runtime = mock_config_entry.runtime_data
    before = set(runtime.known_sensor_unique_ids)
    runtime.discovery_in_progress = True

    await async_discover_all_entities(hass, mock_config_entry)
    assert runtime.known_sensor_unique_ids == before

    runtime.discovery_in_progress = False
