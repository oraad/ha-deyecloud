"""Runtime data types for DeyeCloud."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .api import DeyeCloudApiClient
    from .api_types import MeasurePoint
    from .coordinator import DeyeCloudCoordinator


@dataclass
class DeyeCloudRuntimeData:
    """Runtime data stored on the config entry."""

    client: DeyeCloudApiClient
    coordinator: DeyeCloudCoordinator
    known_sensor_unique_ids: set[str] = field(default_factory=set)
    known_binary_unique_ids: set[str] = field(default_factory=set)
    measure_point_cache: dict[str, list[MeasurePoint]] = field(default_factory=dict)
    missing_device_polls: dict[str, int] = field(default_factory=dict)
    listener_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    listener_pending: bool = False
    discovery_in_progress: bool = False
    add_sensor_entities: AddEntitiesCallback | None = None
    add_binary_sensor_entities: AddEntitiesCallback | None = None


type DeyeCloudConfigEntry = ConfigEntry[DeyeCloudRuntimeData]
