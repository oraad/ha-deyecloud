"""Binary sensor platform for DeyeCloud."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api_types import StationCoordinatorData
from .const import PARALLEL_UPDATES as _PARALLEL_UPDATES
from .data import DeyeCloudConfigEntry
from .entity import DeyeCloudEntity
from .subentry_sync import build_station_subentry_map, register_station_entities

if TYPE_CHECKING:
    from .api_types import Device
    from .coordinator import DeyeCloudCoordinator


PARALLEL_UPDATES = _PARALLEL_UPDATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeyeCloudConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DeyeCloud binary sensors."""
    entry.runtime_data.add_binary_sensor_entities = async_add_entities
    coordinator = entry.runtime_data.coordinator
    register_station_entities(
        entry=entry,
        coordinator_data=coordinator.data,
        async_add_entities=async_add_entities,
        build_fn=lambda station_id, station_data, subentry_id: _build_station_entities(
            coordinator, station_id, station_data, subentry_id
        ),
    )
    entry.runtime_data.known_binary_unique_ids.update(
        _iter_binary_unique_ids(coordinator.data)
    )


def _iter_binary_unique_ids(
    coordinator_data: dict[str, StationCoordinatorData],
) -> set[str]:
    unique_ids: set[str] = set()
    for station_id, station_data in coordinator_data.items():
        for device in station_data.devices:
            unique_ids.add(f"station_{station_id}_dev_{device.device_sn}_online")
    return unique_ids


def _build_station_entities(
    coordinator: DeyeCloudCoordinator,
    station_id: str,
    station_data: StationCoordinatorData,
    subentry_id: str,
) -> list[DeyeCloudOnlineBinarySensor]:
    return [
        DeyeCloudOnlineBinarySensor(
            coordinator,
            station_id=station_id,
            subentry_id=subentry_id,
            device=device,
        )
        for device in station_data.devices
    ]


class DeyeCloudOnlineBinarySensor(DeyeCloudEntity, BinarySensorEntity):
    """Connectivity binary sensor for a DeyeCloud device."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: DeyeCloudCoordinator,
        *,
        station_id: str,
        subentry_id: str,
        device: Device,
    ) -> None:
        super().__init__(
            coordinator,
            station_id=station_id,
            unique_id=f"station_{station_id}_dev_{device.device_sn}_online",
            subentry_id=subentry_id,
            device=device,
        )
        self._attr_translation_key = "device_online"

    @property
    def is_on(self) -> bool | None:
        station = self._station_data()
        if self._device is None or not station:
            return None
        device_data = station.device_data.get(self._device.device_sn)
        if device_data and device_data.device_state is not None:
            return bool(device_data.device_state)
        if self._device.connect_status is not None:
            return bool(self._device.connect_status)
        if self._device.device_state is not None:
            return bool(self._device.device_state)
        return None


def _build_entities_for_entry(
    entry: DeyeCloudConfigEntry,
) -> list[DeyeCloudOnlineBinarySensor]:
    coordinator = entry.runtime_data.coordinator
    station_map = build_station_subentry_map(entry)
    entities: list[DeyeCloudOnlineBinarySensor] = []
    for station_id, station_data in coordinator.data.items():
        subentry_id = station_map.get(station_id)
        if not subentry_id:
            continue
        entities.extend(
            _build_station_entities(coordinator, station_id, station_data, subentry_id)
        )
    return entities


async def async_discover_new_entities(
    hass: HomeAssistant,
    entry: DeyeCloudConfigEntry,
) -> None:
    """Add newly discovered binary sensors at runtime."""
    runtime = entry.runtime_data
    all_entities = _build_entities_for_entry(entry)
    new_entities = [
        entity
        for entity in all_entities
        if entity.unique_id not in runtime.known_binary_unique_ids
    ]
    if not new_entities:
        return

    async_add_entities = runtime.add_binary_sensor_entities
    if not async_add_entities:
        return

    by_subentry: dict[str, list[DeyeCloudOnlineBinarySensor]] = {}
    for entity in new_entities:
        by_subentry.setdefault(entity._subentry_id, []).append(entity)

    for subentry_id, entities in by_subentry.items():
        async_add_entities(entities, config_subentry_id=subentry_id)
        runtime.known_binary_unique_ids.update(
            entity.unique_id for entity in entities if entity.unique_id
        )
