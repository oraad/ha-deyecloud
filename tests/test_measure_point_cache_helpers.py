"""Additional tests for measure point cache helpers."""

from __future__ import annotations

from custom_components.deyecloud.api_types import MeasurePoint
from custom_components.deyecloud.coordinator import DeyeCloudCoordinator
from custom_components.deyecloud.data import DeyeCloudRuntimeData
from custom_components.deyecloud.measure_point_cache import (
    apply_measure_point_cache_to_coordinator,
    prune_measure_point_cache,
)


async def test_apply_and_prune_measure_point_cache(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Apply cached catalogs to coordinator data and prune removed devices."""
    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    runtime = DeyeCloudRuntimeData(client=mock_api_client, coordinator=coordinator)
    mock_config_entry.runtime_data = runtime
    await coordinator.async_refresh()

    runtime.measure_point_cache["INV123"] = [
        MeasurePoint(key="SOC", name="Battery SOC", unit="%")
    ]
    runtime.measure_point_cache["OLD999"] = [
        MeasurePoint(key="SOC", name="Battery SOC", unit="%")
    ]

    apply_measure_point_cache_to_coordinator(mock_config_entry)
    assert coordinator.data["101"].measure_points["INV123"]

    prune_measure_point_cache(mock_config_entry)
    assert "INV123" in runtime.measure_point_cache
    assert "OLD999" not in runtime.measure_point_cache
