"""Diagnostics support for DeyeCloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_APP_SECRET, CONF_PASSWORD
from .data import DeyeCloudConfigEntry

TO_REDACT = {
    CONF_PASSWORD,
    CONF_APP_SECRET,
    "accessToken",
    "refreshToken",
    "token",
    "appSecret",
    "password",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: DeyeCloudConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    return async_redact_data(
        {
            "entry": {
                "title": entry.title,
                "data": dict(entry.data),
                "options": dict(entry.options),
                "subentries": [
                    {
                        "subentry_id": subentry.subentry_id,
                        "subentry_type": subentry.subentry_type,
                        "title": subentry.title,
                        "unique_id": subentry.unique_id,
                        "data": dict(subentry.data),
                    }
                    for subentry in entry.subentries.values()
                ],
            },
            "coordinator": {
                "last_update_success": coordinator.last_update_success,
                "stations": list(coordinator.data.keys()),
                "device_counts": {
                    station_id: len(station.devices)
                    for station_id, station in coordinator.data.items()
                },
            },
            "client": {
                "base_url": entry.data.get("base_url"),
                "has_token": runtime.client.access_token is not None,
            },
        },
        TO_REDACT,
    )
