"""The DeyeCloud integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import DOMAIN, ISSUE_API_UNAVAILABLE, ISSUE_AUTH_FAILED
from .coordinator import DeyeCloudCoordinator
from .data import DeyeCloudConfigEntry, DeyeCloudRuntimeData
from .migration import async_migrate_entry

if TYPE_CHECKING:
    from homeassistant.helpers.typing import ConfigType


__all__ = ["DOMAIN", "PLATFORMS", "async_migrate_entry"]


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the DeyeCloud integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: DeyeCloudConfigEntry) -> bool:
    """Set up DeyeCloud from a config entry."""
    from .api import DeyeCloudApiClient
    from .measure_point_cache import (
        apply_measure_point_cache_to_coordinator,
        async_refresh_measure_point_cache,
    )
    from .subentry_sync import async_sync_station_subentries, build_station_subentry_map

    client = DeyeCloudApiClient(
        session=async_get_clientsession(hass),
        base_url=entry.data["base_url"],
        app_id=entry.data["app_id"],
        app_secret=entry.data["app_secret"],
        username=entry.data["username"],
        password=entry.data["password"],
        company_id=entry.data.get("company_id"),
    )

    coordinator = DeyeCloudCoordinator(hass, entry)

    entry.runtime_data = DeyeCloudRuntimeData(client=client, coordinator=coordinator)

    try:
        await coordinator.async_config_entry_first_refresh()

    except ConfigEntryAuthFailed:
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_AUTH_FAILED,
            is_fixable=True,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_AUTH_FAILED,
        )

        raise

    except UpdateFailed as exc:
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_API_UNAVAILABLE,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_API_UNAVAILABLE,
            translation_placeholders={"error": str(exc)},
        )

        raise

    ir.async_delete_issue(hass, DOMAIN, ISSUE_AUTH_FAILED)

    ir.async_delete_issue(hass, DOMAIN, ISSUE_API_UNAVAILABLE)

    all_devices = [
        device for station in coordinator.data.values() for device in station.devices
    ]

    await async_refresh_measure_point_cache(entry, all_devices)

    apply_measure_point_cache_to_coordinator(entry)

    stations = [station.info for station in coordinator.data.values()]

    had_station_subentries = bool(build_station_subentry_map(entry))
    _, structural_changed, _ = await async_sync_station_subentries(
        hass, entry, stations
    )

    refreshed_entry = hass.config_entries.async_get_entry(entry.entry_id)
    if refreshed_entry is not None:
        entry = refreshed_entry

    if structural_changed and had_station_subentries:
        hass.config_entries.async_schedule_reload(entry.entry_id)

        return True

    def _schedule_coordinator_listener() -> None:

        hass.async_create_task(_async_coordinator_listener(hass, entry))

    entry.async_on_unload(
        coordinator.async_add_listener(_schedule_coordinator_listener)
    )

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: DeyeCloudConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        ir.async_delete_issue(hass, DOMAIN, ISSUE_AUTH_FAILED)

        ir.async_delete_issue(hass, DOMAIN, ISSUE_API_UNAVAILABLE)

    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: DeyeCloudConfigEntry) -> None:

    await hass.config_entries.async_reload(entry.entry_id)


async def _async_coordinator_listener(
    hass: HomeAssistant,
    entry: DeyeCloudConfigEntry,
) -> None:
    """Run post-poll maintenance; queue a trailing pass when polls overlap."""
    runtime = entry.runtime_data

    if runtime.listener_lock.locked():
        runtime.listener_pending = True

        return

    async with runtime.listener_lock:
        while True:
            runtime.listener_pending = False

            await _async_run_coordinator_listener(hass, entry)

            if not runtime.listener_pending:
                break


async def _async_run_coordinator_listener(
    hass: HomeAssistant,
    entry: DeyeCloudConfigEntry,
) -> None:

    from .discovery import async_discover_all_entities
    from .measure_point_cache import (
        apply_measure_point_cache_to_coordinator,
        async_refresh_measure_point_cache,
        prune_measure_point_cache,
    )
    from .stale_entities import async_remove_stale_entities
    from .subentry_sync import async_sync_station_subentries

    runtime = entry.runtime_data
    coordinator_data = runtime.coordinator.data or {}

    if coordinator_data:
        stations = [station.info for station in coordinator_data.values()]
        _, structural_changed, _ = await async_sync_station_subentries(
            hass, entry, stations
        )
        if structural_changed:
            hass.config_entries.async_schedule_reload(entry.entry_id)
            return

        all_devices = [
            device
            for station in coordinator_data.values()
            for device in station.devices
        ]
        await async_refresh_measure_point_cache(entry, all_devices)
        prune_measure_point_cache(entry)
        apply_measure_point_cache_to_coordinator(entry)
        await async_discover_all_entities(hass, entry)

    await async_remove_stale_entities(hass, entry)
