"""Tests for sensor platform."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers import entity_registry as er

from custom_components.deyecloud.api_types import (
    Device,
    OptimizerRecord,
    Station,
    StationCoordinatorData,
)
from custom_components.deyecloud.data import DeyeCloudRuntimeData
from custom_components.deyecloud.sensor import (
    DeyeCloudDeviceSensor,
    DeyeCloudOptimizerSensor,
    DeyeCloudStationSensor,
    DeyeCloudStationStatusSensor,
    _build_station_entities,
    _iter_sensor_unique_ids,
    _timestamp_from_epoch,
)
from tests.conftest import setup_config_entry


async def test_build_station_entities(hass, mock_config_entry, mock_api_client) -> None:
    """Build device and station sensors."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()
    station_data = coordinator.data["101"]
    entities = _build_station_entities(coordinator, "101", station_data, "sub-101")
    assert any(isinstance(entity, DeyeCloudDeviceSensor) for entity in entities)
    assert any(isinstance(entity, DeyeCloudStationSensor) for entity in entities)
    assert entities[0].unique_id.startswith("station_101_")


async def test_build_station_entities_uses_generation_power(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Station sensors are created from production station/latest keys."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()
    station_data = coordinator.data["101"]
    entities = _build_station_entities(coordinator, "101", station_data, "sub-101")
    station_entities = [
        entity for entity in entities if isinstance(entity, DeyeCloudStationSensor)
    ]
    assert any(
        entity.unique_id == "station_101_station_generation_power"
        for entity in station_entities
    )
    assert any(
        entity.unique_id == "station_101_station_battery_soc"
        for entity in station_entities
    )


async def test_station_sensor_names_and_classes(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Station sensors expose distinct names and correct device classes."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()

    generation = DeyeCloudStationSensor(
        coordinator,
        station_id="101",
        subentry_id="sub-101",
        metric_key="generationPower",
    )
    assert generation.name == "Solar generation"
    assert generation.device_class == SensorDeviceClass.POWER
    assert generation.suggested_display_precision == 0

    battery_soc = DeyeCloudStationSensor(
        coordinator,
        station_id="101",
        subentry_id="sub-101",
        metric_key="batterySOC",
    )
    assert battery_soc.name == "Battery SOC"
    assert battery_soc.device_class == SensorDeviceClass.BATTERY
    assert battery_soc.suggested_display_precision == 0


async def test_station_last_update_is_a_timestamp(
    hass, mock_config_entry, mock_api_client
) -> None:
    """A station's last update must surface as a time, not the raw epoch."""
    from unittest.mock import AsyncMock

    from custom_components.deyecloud.api_types import StationData
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    mock_api_client.async_get_station_latest = AsyncMock(
        return_value=StationData(
            station_id="101", data={"lastUpdateTime": 1781963148.0}
        )
    )
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()

    sensor = DeyeCloudStationSensor(
        coordinator,
        station_id="101",
        subentry_id="sub-101",
        metric_key="lastUpdateTime",
    )
    assert sensor.name == "Last update"
    assert sensor.device_class is SensorDeviceClass.TIMESTAMP
    # The timestamp device class is non-numeric, so it must not declare a unit.
    assert sensor.native_unit_of_measurement is None
    assert sensor.state_class is None

    # The value is converted to a real datetime, which is what lets the
    # frontend show a date and a relative time instead of "1781963148".
    value = sensor.native_value
    assert isinstance(value, datetime)
    assert value == datetime(2026, 6, 20, 13, 45, 48, tzinfo=UTC)
    # Home Assistant renders the state with exactly this format, which is what
    # the frontend turns into a date and a relative time.
    assert value.isoformat(timespec="seconds") == "2026-06-20T13:45:48+00:00"


def test_timestamp_from_epoch_filters_unusable_values() -> None:
    """Only a real epoch is converted to a datetime."""
    assert _timestamp_from_epoch(1781963148) == datetime(
        2026, 6, 20, 13, 45, 48, tzinfo=UTC
    )
    # Out of range, wrong type, or a non-numeric string the API might send.
    assert _timestamp_from_epoch(0) is None
    assert _timestamp_from_epoch(-1781963148) is None
    assert _timestamp_from_epoch(1e15) is None
    assert _timestamp_from_epoch(value=True) is None
    assert _timestamp_from_epoch("1781963148") is None
    assert _timestamp_from_epoch(None) is None


async def test_device_sensor_uses_api_name_without_translation(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Untranslated device sensors keep API catalog names."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()
    device = coordinator.data["101"].devices[0]

    entity = DeyeCloudDeviceSensor(
        coordinator,
        station_id="101",
        subentry_id="sub-101",
        device=device,
        point_key="Pv1Voltage",
        point_unit="V",
        point_name="PV1 Voltage",
    )
    assert entity.name == "PV1 Voltage"
    assert entity.translation_key is None
    assert entity.device_class == SensorDeviceClass.VOLTAGE
    assert entity.suggested_display_precision == 1


async def test_device_sensor_last_update_is_a_timestamp(
    hass, mock_config_entry, mock_api_client
) -> None:
    """A timestamp measure point on a device must also return a datetime."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()
    device = coordinator.data["101"].devices[0]
    station = coordinator.data["101"]
    device_sn = device.device_sn
    from custom_components.deyecloud.api_types import DataPoint, DeviceData

    station.device_data[device_sn] = DeviceData(
        device_sn=device_sn,
        device_type="1",
        device_state=1,
        data_list=[DataPoint(key="lastUpdateTime", value="1781963148")],
    )

    entity = DeyeCloudDeviceSensor(
        coordinator,
        station_id="101",
        subentry_id="sub-101",
        device=device,
        point_key="lastUpdateTime",
        point_unit=None,
    )
    assert entity.device_class is SensorDeviceClass.TIMESTAMP
    assert entity.native_value == datetime(2026, 6, 20, 13, 45, 48, tzinfo=UTC)


async def test_device_sensor_energy_key_with_power_suffix(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Energy units are not forced to power by key suffix."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()
    device = coordinator.data["101"].devices[0]

    entity = DeyeCloudDeviceSensor(
        coordinator,
        station_id="101",
        subentry_id="sub-101",
        device=device,
        point_key="gridPower",
        point_unit="kWh",
        point_name="Grid energy",
    )
    assert entity.device_class == SensorDeviceClass.ENERGY
    assert entity.suggested_display_precision == 2


async def test_build_station_entities_adds_station_status_fallback(
    hass, mock_config_entry, mock_api_client
) -> None:
    """A station status sensor is created when station metrics are unavailable."""
    from custom_components.deyecloud.api_types import (
        Station,
        StationCoordinatorData,
        StationData,
    )
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()
    station_data = StationCoordinatorData(
        info=Station(station_id="101", name="Home Plant"),
        devices=coordinator.data["101"].devices,
        device_data=coordinator.data["101"].device_data,
        measure_points=coordinator.data["101"].measure_points,
        station_latest=StationData(station_id="101", data={"unexpectedField": 1}),
    )
    entities = _build_station_entities(coordinator, "101", station_data, "sub-101")
    assert any(isinstance(entity, DeyeCloudStationStatusSensor) for entity in entities)


async def test_build_station_entities_without_station_latest(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Station status sensor is created when station latest data is missing."""
    from custom_components.deyecloud.api_types import Station, StationCoordinatorData
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()
    station_data = StationCoordinatorData(
        info=Station(station_id="101", name="Home Plant"),
        devices=coordinator.data["101"].devices,
        device_data=coordinator.data["101"].device_data,
        measure_points=coordinator.data["101"].measure_points,
        station_latest=None,
    )
    entities = _build_station_entities(coordinator, "101", station_data, "sub-101")
    status_entities = [
        entity
        for entity in entities
        if isinstance(entity, DeyeCloudStationStatusSensor)
    ]
    assert len(status_entities) == 1
    assert status_entities[0].native_value == "ok"


async def test_iter_sensor_unique_ids(hass, mock_config_entry, mock_api_client) -> None:
    """Collect unique ids from coordinator data."""
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    await coordinator.async_refresh()
    unique_ids = _iter_sensor_unique_ids(coordinator.data)
    assert any("dev_INV123" in unique_id for unique_id in unique_ids)


async def test_sensor_setup(hass, mock_config_entry, mock_api_client) -> None:
    """Sensor platform sets up entities."""
    await setup_config_entry(hass, mock_config_entry)

    registry = er.async_get(hass)
    sensor_entities = [
        entity
        for entity in registry.entities.values()
        if entity.config_entry_id == mock_config_entry.entry_id
        and entity.domain == "sensor"
    ]
    assert sensor_entities


async def test_last_update_state_renders_as_a_date(
    hass, mock_config_entry, mock_api_client
) -> None:
    """End to end, the entity state is a date the frontend can render."""
    from unittest.mock import AsyncMock

    from custom_components.deyecloud.api_types import StationData

    mock_api_client.async_get_station_latest = AsyncMock(
        return_value=StationData(
            station_id="101",
            data={
                "generationPower": 12.5,
                "batterySOC": 85.0,
                "lastUpdateTime": 1781963148.0,
            },
        )
    )
    await setup_config_entry(hass, mock_config_entry)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = next(
        entity.entity_id
        for entity in registry.entities.values()
        if entity.config_entry_id == mock_config_entry.entry_id
        and entity.domain == "sensor"
        and entity.unique_id == "station_101_station_last_update_time"
    )

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "2026-06-20T13:45:48+00:00"
    assert state.attributes["device_class"] == "timestamp"
    # Home Assistant would raise on a unit here, so confirm it is absent.
    assert "unit_of_measurement" not in state.attributes


def _optimizer_coordinator(hass, mock_config_entry, mock_api_client, record=None):
    from custom_components.deyecloud.coordinator import DeyeCloudCoordinator

    mock_config_entry.add_to_hass(hass)
    coordinator = DeyeCloudCoordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = DeyeCloudRuntimeData(
        client=mock_api_client,
        coordinator=coordinator,
    )
    coordinator.data = {
        "101": StationCoordinatorData(
            info=Station(
                station_id="101",
                name="Home Plant",
                raw={"regionTimezone": "Asia/Kolkata"},
            ),
            devices=[
                Device(
                    device_sn="OPT123",
                    device_type="OPTIMIZER",
                    station_id="101",
                    connect_status=1,
                ),
                Device(
                    device_sn="CONC1",
                    device_type="OPTIMIZER_CONCENTRATOR",
                    station_id="101",
                    connect_status=1,
                ),
            ],
            device_data={},
            measure_points={},
            optimizers={"OPT123": record} if record else {},
        )
    }
    return coordinator


def _optimizer_entities(coordinator):
    return [
        entity
        for entity in _build_station_entities(
            coordinator, "101", coordinator.data["101"], "sub-101"
        )
        if isinstance(entity, DeyeCloudOptimizerSensor)
    ]


def test_optimizer_sensors_are_created(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Each panel optimizer gets three history sensors; the concentrator gets none."""
    coordinator = _optimizer_coordinator(hass, mock_config_entry, mock_api_client)
    entities = _optimizer_entities(coordinator)
    assert [entity._field for entity in entities] == [
        "production_today",
        "production_month",
        "average_power",
    ]
    assert [entity.unique_id for entity in entities] == [
        "station_101_opt_OPT123_production_today",
        "station_101_opt_OPT123_production_month",
        "station_101_opt_OPT123_average_power",
    ]


def test_optimizer_sensor_units_and_classes(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Energy sensors are resettable totals; power is a measurement."""
    from homeassistant.components.sensor import SensorStateClass

    coordinator = _optimizer_coordinator(hass, mock_config_entry, mock_api_client)
    today, month, power = _optimizer_entities(coordinator)

    for energy in (today, month):
        assert energy.device_class == SensorDeviceClass.ENERGY
        assert energy.state_class == SensorStateClass.TOTAL
        assert energy.native_unit_of_measurement == "kWh"

    assert power.device_class == SensorDeviceClass.POWER
    assert power.state_class == SensorStateClass.MEASUREMENT
    assert power.native_unit_of_measurement == "W"


def test_optimizer_sensor_values(hass, mock_config_entry, mock_api_client) -> None:
    """Native values come from the derived record."""
    coordinator = _optimizer_coordinator(
        hass,
        mock_config_entry,
        mock_api_client,
        record=OptimizerRecord(
            device_sn="OPT123",
            date="2026-09-28",
            today=0.42,
            month=7.7,
            power=5400.0,
            online=True,
        ),
    )
    today, month, power = _optimizer_entities(coordinator)
    assert today.native_value == 0.42
    assert month.native_value == 7.7
    assert power.native_value == 5400.0
    assert today.available is True
    assert today.extra_state_attributes["local_day"] == "2026-09-28"
    assert today.extra_state_attributes["online"] is True


def test_optimizer_sensor_unavailable_without_record(
    hass, mock_config_entry, mock_api_client
) -> None:
    """A missing record reports unavailable rather than a broken entity."""
    coordinator = _optimizer_coordinator(hass, mock_config_entry, mock_api_client)
    today, _month, power = _optimizer_entities(coordinator)
    assert today.native_value is None
    assert today.available is False
    assert power.available is False


def test_optimizer_sensor_last_reset_uses_plant_timezone(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Energy resets are anchored to the plant's local midnight."""
    from datetime import timedelta

    coordinator = _optimizer_coordinator(
        hass,
        mock_config_entry,
        mock_api_client,
        record=OptimizerRecord(
            device_sn="OPT123", date="2026-09-28", today=0.42, month=7.7
        ),
    )
    today, month, power = _optimizer_entities(coordinator)

    today_reset = today.last_reset
    assert today_reset is not None
    assert today_reset.utcoffset() == timedelta(hours=5, minutes=30)
    assert today_reset.day == 28

    month_reset = month.last_reset
    assert month_reset is not None
    assert month_reset.day == 1
    assert month_reset.month == 9

    # Power is a rate, so it has no reset point.
    assert power.last_reset is None


def test_optimizer_unique_ids_included_in_discovery(
    hass, mock_config_entry, mock_api_client
) -> None:
    """Optimizer sensors take part in runtime discovery."""
    coordinator = _optimizer_coordinator(hass, mock_config_entry, mock_api_client)
    unique_ids = _iter_sensor_unique_ids(coordinator.data)
    assert "station_101_opt_OPT123_production_today" in unique_ids
    assert "station_101_opt_OPT123_average_power" in unique_ids
