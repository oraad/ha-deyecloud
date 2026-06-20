"""Unified runtime entity discovery for DeyeCloud."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import binary_sensor, sensor

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import DeyeCloudConfigEntry


async def async_discover_all_entities(
    hass: HomeAssistant,
    entry: DeyeCloudConfigEntry,
) -> None:
    """Discover new sensor and binary_sensor entities under a single lock."""
    runtime = entry.runtime_data
    if runtime.discovery_in_progress:
        return

    runtime.discovery_in_progress = True
    try:
        await sensor.async_discover_new_entities(hass, entry)
        await binary_sensor.async_discover_new_entities(hass, entry)
    finally:
        runtime.discovery_in_progress = False
