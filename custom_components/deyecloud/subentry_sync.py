"""Sync DeyeCloud plant config subentries."""

from __future__ import annotations

import logging
from collections.abc import Callable
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant

from .api_types import Station
from .const import CONF_SELECTED_PLANTS, CONF_STATION_ID, SUBENTRY_TYPE_PLANT

_LOGGER = logging.getLogger(__name__)


def normalize_station_id(value: Any) -> str | None:
    """Return a normalized station id string."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.removesuffix(".0")
    return text


def get_station_id(station: dict[str, Any] | Station) -> str | None:
    """Return normalized station id from API or model data."""
    if isinstance(station, Station):
        return normalize_station_id(station.station_id)
    return normalize_station_id(station.get("id") or station.get("stationId"))


def station_display_name(station: dict[str, Any] | Station, station_id: str) -> str:
    """Return a human-readable plant name."""
    if isinstance(station, Station):
        return station.name
    return station.get("name") or station.get("stationName") or f"Plant {station_id}"


def get_selected_station_ids(entry: ConfigEntry) -> set[str] | None:
    """Return selected plant ids, or None when all API plants should load."""
    if CONF_SELECTED_PLANTS not in entry.options:
        return None
    selected: set[str] = set()
    for station_id in entry.options[CONF_SELECTED_PLANTS]:
        normalized = normalize_station_id(station_id)
        if normalized:
            selected.add(normalized)
    return selected


def filter_stations_by_selection(
    stations: list[Station],
    entry: ConfigEntry,
) -> list[Station]:
    """Return only plants the user chose to load."""
    selected = get_selected_station_ids(entry)
    if selected is None:
        return stations
    return [station for station in stations if station.station_id in selected]


def build_plant_subentry_map(entry: ConfigEntry) -> dict[str, str]:
    """Return station_id -> subentry_id for plant subentries."""
    plant_map: dict[str, str] = {}
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_PLANT:
            continue
        station_id = normalize_station_id(subentry.data.get(CONF_STATION_ID))
        if station_id:
            plant_map[station_id] = subentry.subentry_id
    return plant_map


def register_plant_entities(
    *,
    entry: ConfigEntry,
    coordinator_data: dict[str, Any],
    async_add_entities: Callable[..., None],
    build_fn: Callable[[str, Any, str], list[Any]],
) -> int:
    """Register entities for all plants using their subentries."""
    plant_map = build_plant_subentry_map(entry)
    if not plant_map:
        if coordinator_data:
            _LOGGER.error("No plant subentries configured for DeyeCloud entry")
        return 0

    total = 0
    for station_id, station_data in coordinator_data.items():
        norm_id = normalize_station_id(station_id) or str(station_id)
        subentry_id = plant_map.get(norm_id)
        if not subentry_id:
            _LOGGER.warning("No plant subentry for station %s", norm_id)
            continue
        station_entities = build_fn(norm_id, station_data, subentry_id)
        if station_entities:
            async_add_entities(station_entities, config_subentry_id=subentry_id)
            total += len(station_entities)
    return total


def _plant_subentries_by_station_id(entry: ConfigEntry) -> dict[str, ConfigSubentry]:
    result: dict[str, ConfigSubentry] = {}
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_PLANT:
            continue
        if CONF_STATION_ID not in subentry.data:
            continue
        station_id = normalize_station_id(subentry.data[CONF_STATION_ID])
        if station_id:
            result[station_id] = subentry
    return result


async def async_sync_plant_subentries(
    hass: HomeAssistant,
    entry: ConfigEntry,
    stations: list[Station],
) -> tuple[dict[str, ConfigSubentry], bool, bool]:
    """Ensure plant subentries match selected API stations."""
    stations = filter_stations_by_selection(stations, entry)
    api_stations = {station.station_id: station for station in stations}
    structural_changed = False
    metadata_changed = False
    current_entry = hass.config_entries.async_get_entry(entry.entry_id)
    if current_entry is None:
        return {}, False, False

    existing = _plant_subentries_by_station_id(current_entry)
    for station_id, subentry in list(existing.items()):
        if station_id not in api_stations:
            _LOGGER.info("Removing stale plant subentry for station %s", station_id)
            hass.config_entries.async_remove_subentry(
                current_entry, subentry.subentry_id
            )
            structural_changed = True
            current_entry = hass.config_entries.async_get_entry(entry.entry_id)
            if current_entry is None:
                return {}, structural_changed, metadata_changed
            existing = _plant_subentries_by_station_id(current_entry)

    for station_id, station in api_stations.items():
        title = station_display_name(station, station_id)
        if station_id in existing:
            subentry = existing[station_id]
            if subentry.title != title:
                current_entry = hass.config_entries.async_get_entry(entry.entry_id)
                if current_entry is None:
                    return {}, structural_changed, metadata_changed
                refreshed_subentry = current_entry.subentries.get(subentry.subentry_id)
                if refreshed_subentry is None:
                    continue
                if hass.config_entries.async_update_subentry(
                    current_entry,
                    refreshed_subentry,
                    title=title,
                ):
                    metadata_changed = True
            continue

        subentry = ConfigSubentry(
            data=MappingProxyType({CONF_STATION_ID: station_id}),
            subentry_type=SUBENTRY_TYPE_PLANT,
            title=title,
            unique_id=station_id,
        )
        current_entry = hass.config_entries.async_get_entry(entry.entry_id)
        if current_entry is None:
            return {}, structural_changed, metadata_changed
        hass.config_entries.async_add_subentry(current_entry, subentry)
        _LOGGER.info("Added plant subentry for station %s (%s)", station_id, title)
        structural_changed = True

    final_entry = hass.config_entries.async_get_entry(entry.entry_id)
    if final_entry is None:
        return {}, structural_changed, metadata_changed

    return (
        _plant_subentries_by_station_id(final_entry),
        structural_changed,
        metadata_changed,
    )
