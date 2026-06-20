"""Sensor platform for DeyeCloud."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api_types import Device, PlantCoordinatorData
from .const import PARALLEL_UPDATES as _PARALLEL_UPDATES
from .data import DeyeCloudConfigEntry
from .entity import DeyeCloudEntity
from .measure_point_cache import iter_device_measure_specs
from .measure_points import (
    friendly_measure_name,
    map_unit_to_sensor_classes,
    measure_point_translation_key,
    normalize_measure_key,
    parse_numeric_value,
)
from .subentry_sync import build_plant_subentry_map, register_plant_entities

if TYPE_CHECKING:
    from .coordinator import DeyeCloudCoordinator

_STATION_METRIC_KEYS = (
    "generationValue",
    "consumptionValue",
    "gridValue",
    "purchaseValue",
    "chargeValue",
    "dischargeValue",
    "currentPower",
    "gridPower",
    "buyPower",
    "sellPower",
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
    register_plant_entities(
        entry=entry,
        coordinator_data=coordinator.data,
        async_add_entities=async_add_entities,
        build_fn=lambda station_id, plant_data, subentry_id: _build_station_entities(
            coordinator, station_id, plant_data, subentry_id
        ),
    )
    entry.runtime_data.known_sensor_unique_ids.update(
        _iter_sensor_unique_ids(coordinator.data)
    )


def _iter_sensor_unique_ids(
    coordinator_data: dict[str, PlantCoordinatorData],
) -> set[str]:
    unique_ids: set[str] = set()
    for station_id, plant_data in coordinator_data.items():
        unique_ids.update(_plant_sensor_unique_ids(station_id, plant_data))
    return unique_ids


def _plant_sensor_unique_ids(
    station_id: str,
    plant_data: PlantCoordinatorData,
) -> set[str]:
    unique_ids = {
        f"plant_{station_id}_station_{normalize_measure_key(key)}"
        for key in _STATION_METRIC_KEYS
        if plant_data.station_latest and key in plant_data.station_latest.data
    }
    for device in plant_data.devices:
        for point_key, _point_unit in iter_device_measure_specs(
            device.device_sn, plant_data
        ):
            unique_ids.add(
                f"plant_{station_id}_dev_{device.device_sn}_"
                f"{normalize_measure_key(point_key)}"
            )
    return unique_ids


def _build_station_entities(
    coordinator: DeyeCloudCoordinator,
    station_id: str,
    plant_data: PlantCoordinatorData,
    subentry_id: str,
) -> list[DeyeCloudSensor]:
    entities: list[DeyeCloudSensor] = []

    if plant_data.station_latest:
        for key in _STATION_METRIC_KEYS:
            if key not in plant_data.station_latest.data:
                continue
            entities.append(
                DeyeCloudStationSensor(
                    coordinator,
                    station_id=station_id,
                    subentry_id=subentry_id,
                    metric_key=key,
                )
            )

    for device in plant_data.devices:
        catalog = {
            point.key: point
            for point in plant_data.measure_points.get(device.device_sn, [])
        }
        for point_key, point_unit in iter_device_measure_specs(
            device.device_sn, plant_data
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
    """Plant-level sensor from station latest data."""

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
            unique_id=f"plant_{station_id}_station_{normalize_measure_key(metric_key)}",
            subentry_id=subentry_id,
            device=None,
        )
        self._attr_translation_key = (
            f"station_metric_{normalize_measure_key(metric_key)}"
        )
        (
            self._attr_device_class,
            self._attr_state_class,
            self._attr_native_unit_of_measurement,
            self._attr_entity_category,
            self._attr_entity_registry_enabled_default,
        ) = map_unit_to_sensor_classes(None, metric_key)

    @property
    def native_value(self) -> float | int | str | None:
        plant = self._plant_data()
        if not plant or not plant.station_latest:
            return None
        value = plant.station_latest.data.get(self._metric_key)
        if value is None:
            return None
        return parse_numeric_value(str(value))


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
                f"plant_{station_id}_dev_{device.device_sn}_"
                f"{normalize_measure_key(point_key)}"
            ),
            subentry_id=subentry_id,
            device=device,
        )
        self._attr_translation_key = measure_point_translation_key(point_key)
        self._attr_name = friendly_measure_name(point_key, point_name)
        self._attr_suggested_display_precision = 2
        (
            self._attr_device_class,
            self._attr_state_class,
            self._attr_native_unit_of_measurement,
            self._attr_entity_category,
            self._attr_entity_registry_enabled_default,
        ) = map_unit_to_sensor_classes(point_unit, point_key)

    @property
    def native_value(self) -> float | int | str | None:
        plant = self._plant_data()
        if self._device is None or not plant:
            return None
        device_data = plant.device_data.get(self._device.device_sn)
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
        plant = self._plant_data()
        if self._device and plant:
            device_data = plant.device_data.get(self._device.device_sn)
            if device_data and device_data.collection_time is not None:
                attrs["collection_time"] = device_data.collection_time
        return attrs


def _build_entities_for_entry(entry: DeyeCloudConfigEntry) -> list[DeyeCloudSensor]:
    coordinator = entry.runtime_data.coordinator
    plant_map = build_plant_subentry_map(entry)
    entities: list[DeyeCloudSensor] = []
    for station_id, plant_data in coordinator.data.items():
        subentry_id = plant_map.get(station_id)
        if not subentry_id:
            continue
        entities.extend(
            _build_station_entities(coordinator, station_id, plant_data, subentry_id)
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
