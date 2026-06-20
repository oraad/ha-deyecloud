"""Shared stale entity removal for DeyeCloud."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import STALE_DEVICE_MISSING_POLLS

if TYPE_CHECKING:
    from .data import DeyeCloudConfigEntry


def _device_sn_from_unique_id(unique_id: str, domain: str) -> str | None:
    """Extract device serial from a DeyeCloud entity unique id."""
    if "_dev_" not in unique_id:
        return None
    suffix = unique_id.split("_dev_", 1)[1]
    if domain == "binary_sensor" and suffix.endswith("_online"):
        return suffix[: -len("_online")]
    if domain == "sensor":
        parts = suffix.split("_", 1)
        return parts[0] if parts else None
    return None


async def async_remove_stale_entities(
    hass: HomeAssistant,
    entry: DeyeCloudConfigEntry,
) -> None:
    """Remove sensor and binary_sensor entities for devices gone from the API."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    active_sns = {
        device.device_sn
        for plant in coordinator.data.values()
        for device in plant.devices
    }

    entity_registry = er.async_get(hass)
    missing_sns: set[str] = set()
    entities_by_sn: dict[str, list[er.RegistryEntry]] = {}

    for entity in entity_registry.entities.values():
        if entity.config_entry_id != entry.entry_id:
            continue
        if entity.domain not in {"sensor", "binary_sensor"}:
            continue
        unique_id = entity.unique_id or ""
        device_sn = _device_sn_from_unique_id(unique_id, entity.domain)
        if not device_sn:
            continue
        if device_sn not in active_sns:
            missing_sns.add(device_sn)
            entities_by_sn.setdefault(device_sn, []).append(entity)

    for device_sn in missing_sns:
        runtime.missing_device_polls[device_sn] = (
            runtime.missing_device_polls.get(device_sn, 0) + 1
        )

    for device_sn in active_sns:
        runtime.missing_device_polls.pop(device_sn, None)

    stale_sns = {
        device_sn
        for device_sn, count in runtime.missing_device_polls.items()
        if count >= STALE_DEVICE_MISSING_POLLS
    }
    if not stale_sns:
        return

    for device_sn in stale_sns:
        for entity in entities_by_sn.get(device_sn, []):
            entity_registry.async_remove(entity.entity_id)
            unique_id = entity.unique_id
            if not unique_id:
                continue
            if entity.domain == "sensor":
                runtime.known_sensor_unique_ids.discard(unique_id)
            elif entity.domain == "binary_sensor":
                runtime.known_binary_unique_ids.discard(unique_id)
