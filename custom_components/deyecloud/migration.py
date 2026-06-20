"""Config entry migration for DeyeCloud."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_SELECTED_STATIONS,
    SUBENTRY_TYPE_STATION,
)

_LEGACY_SUBENTRY_TYPE = "plant"
_LEGACY_OPTIONS_KEY = "selected_plants"
_LEGACY_UNIQUE_ID_PREFIX = "plant_"
_STATION_UNIQUE_ID_PREFIX = "station_"


def _migrate_options(options: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(options)
    if _LEGACY_OPTIONS_KEY in migrated:
        migrated[CONF_SELECTED_STATIONS] = migrated.pop(_LEGACY_OPTIONS_KEY)
    return migrated


def _migrate_subentries(hass: HomeAssistant, entry: ConfigEntry) -> None:
    current = hass.config_entries.async_get_entry(entry.entry_id)
    if current is None:
        return

    for subentry in list(current.subentries.values()):
        if subentry.subentry_type != _LEGACY_SUBENTRY_TYPE:
            continue
        hass.config_entries.async_remove_subentry(current, subentry.subentry_id)
        current = hass.config_entries.async_get_entry(entry.entry_id)
        if current is None:
            return
        hass.config_entries.async_add_subentry(
            current,
            ConfigSubentry(
                data=subentry.data,
                subentry_type=SUBENTRY_TYPE_STATION,
                title=subentry.title,
                unique_id=subentry.unique_id,
            ),
        )
        current = hass.config_entries.async_get_entry(entry.entry_id)
        if current is None:
            return


def _migrate_entity_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    entity_registry = er.async_get(hass)
    for entity in entity_registry.entities.values():
        if entity.config_entry_id != entry.entry_id:
            continue
        unique_id = entity.unique_id
        if not unique_id or not unique_id.startswith(_LEGACY_UNIQUE_ID_PREFIX):
            continue
        new_unique_id = unique_id.replace(
            _LEGACY_UNIQUE_ID_PREFIX, _STATION_UNIQUE_ID_PREFIX, 1
        )
        entity_registry.async_update_entity(
            entity.entity_id, new_unique_id=new_unique_id
        )


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to the latest version."""
    if entry.version == 1:
        _migrate_subentries(hass, entry)
        options = _migrate_options(dict(entry.options))
        hass.config_entries.async_update_entry(entry, options=options, version=2)
        refreshed = hass.config_entries.async_get_entry(entry.entry_id)
        if refreshed is not None:
            _migrate_entity_unique_ids(hass, refreshed)
        return True
    return True
