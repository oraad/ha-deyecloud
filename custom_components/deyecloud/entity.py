"""Base entity for DeyeCloud."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, device_type_label
from .coordinator import DeyeCloudCoordinator

if TYPE_CHECKING:
    from .api_types import Device, PlantCoordinatorData


class DeyeCloudEntity(CoordinatorEntity[DeyeCloudCoordinator]):
    """Base DeyeCloud entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DeyeCloudCoordinator,
        *,
        station_id: str,
        unique_id: str,
        subentry_id: str,
        device: Device | None = None,
    ) -> None:
        """Initialize base entity."""
        super().__init__(coordinator)
        self._station_id = station_id
        self._subentry_id = subentry_id
        self._device = device
        self._attr_unique_id = unique_id
        self._attr_device_info = self._build_device_info()

    def _plant_data(self) -> PlantCoordinatorData | None:
        return self.coordinator.data.get(self._station_id)

    def _build_device_info(self) -> DeviceInfo:
        plant_data = self._plant_data()
        plant_name = plant_data.info.name if plant_data else f"Plant {self._station_id}"

        if self._device is not None:
            label = device_type_label(self._device.device_type)
            info = DeviceInfo(
                identifiers={(DOMAIN, self._device.device_sn)},
                name=f"{plant_name} {label} {self._device.device_sn}",
                manufacturer="Deye",
                model=label,
                serial_number=self._device.device_sn,
                via_device=(DOMAIN, f"station_{self._station_id}"),
            )
            return info

        return DeviceInfo(
            identifiers={(DOMAIN, f"station_{self._station_id}")},
            name=plant_name,
            manufacturer="Deye",
            model="Plant",
        )
