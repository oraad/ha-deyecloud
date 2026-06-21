"""Sensor platform for DeyeCloud."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api_types import Device, StationCoordinatorData
from .const import PARALLEL_UPDATES as _PARALLEL_UPDATES
from .data import DeyeCloudConfigEntry
from .entity import DeyeCloudEntity
from .measure_point_cache import iter_device_measure_specs
from .measure_points import (
    friendly_measure_name,
    has_measure_point_translation,
    map_unit_to_sensor_classes,
    measure_point_translation_key,
    normalize_measure_key,
    parse_numeric_value,
    station_metric_label,
)
from .subentry_sync import build_station_subentry_map, register_station_entities

if TYPE_CHECKING:
    from .coordinator import DeyeCloudCoordinator

_STATION_METRIC_KEYS = (
    "generationPower",
    "consumptionPower",
    "gridPower",
    "purchasePower",
    "chargePower",
    "dischargePower",
    "batteryPower",
    "batterySOC",
    "wirePower",
    "lastUpdateTime",
)


PARALLEL_UPDATES = _PARALLEL_UPDATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeyeCloudConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DeyeCloud sensors."""
    entry.runtime_data.add_sensor_entities = async_add_entities
    coordinator = entry.runtime_data.coordinator
    register_station_entities(
        entry=entry,
        coordinator_data=coordinator.data,
        async_add_entities=async_add_entities,
        build_fn=lambda station_id, station_data, subentry_id: _build_station_entities(
            coordinator, station_id, station_data, subentry_id
        ),
    )
    entry.runtime_data.known_sensor_unique_ids.update(
        _iter_sensor_unique_ids(coordinator.data)
    )


def _iter_sensor_unique_ids(
    coordinator_data: dict[str, StationCoordinatorData],
) -> set[str]:
    unique_ids: set[str] = set()
    for station_id, station_data in coordinator_data.items():
        unique_ids.update(_station_sensor_unique_ids(station_id, station_data))
    return unique_ids


def _station_sensor_unique_ids(
    station_id: str,
    station_data: StationCoordinatorData,
) -> set[str]:
    unique_ids: set[str] = set()
    if station_data.station_latest:
        for key in _STATION_METRIC_KEYS:
            if key in station_data.station_latest.data:
                unique_ids.add(
                    f"station_{station_id}_station_{normalize_measure_key(key)}"
                )
        if not unique_ids:
            unique_ids.add(f"station_{station_id}_station_status")
    else:
        unique_ids.add(f"station_{station_id}_station_status")
    for device in station_data.devices:
        for point_key, _point_unit in iter_device_measure_specs(
            device.device_sn, station_data
        ):
            unique_ids.add(
                f"station_{station_id}_dev_{device.device_sn}_"
                f"{normalize_measure_key(point_key)}"
            )
    return unique_ids


def _build_station_entities(
    coordinator: DeyeCloudCoordinator,
    station_id: str,
    station_data: StationCoordinatorData,
    subentry_id: str,
) -> list[DeyeCloudSensor]:
    entities: list[DeyeCloudSensor] = []
    station_entities_added = False

    if station_data.station_latest:
        for key in _STATION_METRIC_KEYS:
            if key not in station_data.station_latest.data:
                continue
            entities.append(
                DeyeCloudStationSensor(
                    coordinator,
                    station_id=station_id,
                    subentry_id=subentry_id,
                    metric_key=key,
                )
            )
            station_entities_added = True

    if not station_entities_added:
        entities.append(
            DeyeCloudStationStatusSensor(
                coordinator,
                station_id=station_id,
                subentry_id=subentry_id,
            )
        )

    for device in station_data.devices:
        catalog = {
            point.key: point
            for point in station_data.measure_points.get(device.device_sn, [])
        }
        for point_key, point_unit in iter_device_measure_specs(
            device.device_sn, station_data
        ):
            catalog_point = catalog.get(point_key)
            entities.append(
                DeyeCloudDeviceSensor(
                    coordinator,
                    station_id=station_id,
                    subentry_id=subentry_id,
                    device=device,
                    point_key=point_key,
                    point_unit=point_unit,
                    point_name=catalog_point.name if catalog_point else None,
                )
            )
    return entities


class DeyeCloudSensor(DeyeCloudEntity, SensorEntity):
    """Base DeyeCloud sensor."""


class DeyeCloudStationSensor(DeyeCloudSensor):
    """Station-level sensor from station latest data."""

    def __init__(
        self,
        coordinator: DeyeCloudCoordinator,
        *,
        station_id: str,
        subentry_id: str,
        metric_key: str,
    ) -> None:
        self._metric_key = metric_key
        super().__init__(
            coordinator,
            station_id=station_id,
            unique_id=f"station_{station_id}_station_{normalize_measure_key(metric_key)}",
            subentry_id=subentry_id,
            device=None,
        )
        self._attr_translation_key = (
            f"station_metric_{normalize_measure_key(metric_key)}"
        )
        self._attr_name = station_metric_label(metric_key)
        (
            self._attr_device_class,
            self._attr_state_class,
            self._attr_native_unit_of_measurement,
            self._attr_entity_category,
            self._attr_entity_registry_enabled_default,
            display_precision,
        ) = map_unit_to_sensor_classes(None, metric_key)
        if display_precision is not None:
            self._attr_suggested_display_precision = display_precision

    @property
    def native_value(self) -> float | int | str | None:
        station = self._station_data()
        if not station or not station.station_latest:
            return None
        value = station.station_latest.data.get(self._metric_key)
        if value is None:
            return None
        return parse_numeric_value(str(value))


class DeyeCloudStationStatusSensor(DeyeCloudSensor):
    """Fallback station sensor that ensures the station device exists."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: DeyeCloudCoordinator,
        *,
        station_id: str,
        subentry_id: str,
    ) -> None:
        super().__init__(
            coordinator,
            station_id=station_id,
            unique_id=f"station_{station_id}_station_status",
            subentry_id=subentry_id,
            device=None,
        )
        self._attr_translation_key = "station_status"

    @property
    def native_value(self) -> str:
        station = self._station_data()
        if not station:
            return "unknown"
        if station.devices:
            return "ok"
        return "no_devices"


class DeyeCloudDeviceSensor(DeyeCloudSensor):
    """Device telemetry sensor."""

    def __init__(
        self,
        coordinator: DeyeCloudCoordinator,
        *,
        station_id: str,
        subentry_id: str,
        device: Device,
        point_key: str,
        point_unit: str | None,
        point_name: str | None = None,
    ) -> None:
        self._point_key = point_key
        super().__init__(
            coordinator,
            station_id=station_id,
            unique_id=(
                f"station_{station_id}_dev_{device.device_sn}_"
                f"{normalize_measure_key(point_key)}"
            ),
            subentry_id=subentry_id,
            device=device,
        )
        self._attr_name = friendly_measure_name(point_key, point_name)
        if has_measure_point_translation(point_key):
            self._attr_translation_key = measure_point_translation_key(point_key)
        (
            self._attr_device_class,
            self._attr_state_class,
            self._attr_native_unit_of_measurement,
            self._attr_entity_category,
            self._attr_entity_registry_enabled_default,
            display_precision,
        ) = map_unit_to_sensor_classes(point_unit, point_key)
        if display_precision is not None:
            self._attr_suggested_display_precision = display_precision

    @property
    def native_value(self) -> float | int | str | None:
        station = self._station_data()
        if self._device is None or not station:
            return None
        device_data = station.device_data.get(self._device.device_sn)
        if not device_data:
            return None
        for point in device_data.data_list:
            if point.key == self._point_key:
                return parse_numeric_value(point.value)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        attrs: dict[str, str | int | None] = {
            "device_sn": self._device.device_sn if self._device else None,
            "measure_key": self._point_key,
        }
        if self._device and self._device.device_type:
            attrs["device_type"] = self._device.device_type
        station = self._station_data()
        if self._device and station:
            device_data = station.device_data.get(self._device.device_sn)
            if device_data and device_data.collection_time is not None:
                attrs["collection_time"] = device_data.collection_time
        return attrs


def _build_entities_for_entry(entry: DeyeCloudConfigEntry) -> list[DeyeCloudSensor]:
    coordinator = entry.runtime_data.coordinator
    station_map = build_station_subentry_map(entry)
    entities: list[DeyeCloudSensor] = []
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
    """Add newly discovered sensors at runtime."""
    runtime = entry.runtime_data
    all_entities = _build_entities_for_entry(entry)
    new_entities = [
        entity
        for entity in all_entities
        if entity.unique_id not in runtime.known_sensor_unique_ids
    ]
    if not new_entities:
        return

    by_subentry: dict[str, list[DeyeCloudSensor]] = {}
    for entity in new_entities:
        by_subentry.setdefault(entity._subentry_id, []).append(entity)

    async_add_entities = runtime.add_sensor_entities
    if not async_add_entities:
        return

    for subentry_id, entities in by_subentry.items():
        async_add_entities(entities, config_subentry_id=subentry_id)
        runtime.known_sensor_unique_ids.update(
            entity.unique_id for entity in entities if entity.unique_id
        )
