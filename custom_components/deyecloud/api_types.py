"""Typed API models for DeyeCloud."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MeasurePoint:
    """A supported telemetry key for a device."""

    key: str
    name: str | None = None
    unit: str | None = None


@dataclass(slots=True)
class DataPoint:
    """A single telemetry value from device latest."""

    key: str
    value: str
    unit: str | None = None
    name: str | None = None


@dataclass(slots=True)
class Device:
    """A DeyeCloud device belonging to a station."""

    device_sn: str
    device_type: str | None
    station_id: str
    device_id: str | None = None
    device_state: int | None = None
    connect_status: int | None = None
    product_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DeviceData:
    """Latest telemetry for a device."""

    device_sn: str
    device_type: str | None
    device_state: int | None
    data_list: list[DataPoint]
    collection_time: str | None = None


@dataclass(slots=True)
class Station:
    """A DeyeCloud station (plant)."""

    station_id: str
    name: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StationData:
    """Latest telemetry for a station."""

    station_id: str
    data: dict[str, Any]


@dataclass(slots=True)
class StationCoordinatorData:
    """Coordinator payload for one station."""

    info: Station
    devices: list[Device]
    device_data: dict[str, DeviceData]
    measure_points: dict[str, list[MeasurePoint]]
    station_latest: StationData | None = None


CoordinatorData = dict[str, StationCoordinatorData]
