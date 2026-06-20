"""Tests for measure point helpers."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower

from custom_components.deyecloud.measure_points import (
    friendly_measure_name,
    map_unit_to_sensor_classes,
    measure_point_translation_key,
    normalize_measure_key,
    parse_numeric_value,
)


def test_normalize_measure_key() -> None:
    """Normalize API keys."""
    assert normalize_measure_key("TotalGridPower") == "total_grid_power"
    assert normalize_measure_key("SOC") == "soc"


def test_friendly_measure_name() -> None:
    """Prefer API provided names."""
    assert friendly_measure_name("SOC", "Battery SOC") == "Battery SOC"
    assert friendly_measure_name("TotalGridPower") == "Total Grid Power"


def test_measure_point_translation_key() -> None:
    """Build translation keys matching strings.json entity.sensor entries."""
    assert measure_point_translation_key("SOC") == "soc"


def test_map_unit_to_sensor_classes() -> None:
    """Map units to HA classes."""
    device_class, state_class, unit, category, enabled = map_unit_to_sensor_classes(
        "kWh", "generationValue"
    )
    assert device_class == SensorDeviceClass.ENERGY
    assert state_class == SensorStateClass.TOTAL
    assert unit == UnitOfEnergy.KILO_WATT_HOUR
    assert category is None
    assert enabled is True

    device_class, state_class, unit, category, enabled = map_unit_to_sensor_classes(
        "W", "TotalGridPower"
    )
    assert device_class == SensorDeviceClass.POWER
    assert unit == UnitOfPower.WATT

    device_class, state_class, unit, category, enabled = map_unit_to_sensor_classes(
        "%", "SOC"
    )
    assert device_class == SensorDeviceClass.BATTERY
    assert unit == PERCENTAGE

    device_class, state_class, unit, category, enabled = map_unit_to_sensor_classes(
        None, "collectionTime"
    )
    assert enabled is False

    device_class, state_class, unit, category, enabled = map_unit_to_sensor_classes(
        "Wh", "energy"
    )
    assert device_class == SensorDeviceClass.ENERGY
    assert unit == UnitOfEnergy.WATT_HOUR

    device_class, state_class, unit, category, enabled = map_unit_to_sensor_classes(
        "V", "voltage"
    )
    assert device_class == SensorDeviceClass.VOLTAGE

    device_class, state_class, unit, category, enabled = map_unit_to_sensor_classes(
        "A", "current"
    )
    assert device_class == SensorDeviceClass.CURRENT

    device_class, state_class, unit, category, enabled = map_unit_to_sensor_classes(
        "°C", "temperature"
    )
    assert device_class == SensorDeviceClass.TEMPERATURE

    device_class, state_class, unit, category, enabled = map_unit_to_sensor_classes(
        "Hz", "frequency"
    )
    assert device_class == SensorDeviceClass.FREQUENCY

    device_class, state_class, unit, category, enabled = map_unit_to_sensor_classes(
        None, "device_state"
    )
    assert enabled is True
    assert category is not None


def test_map_unit_to_sensor_classes_station_metrics() -> None:
    """Map production station/latest keys without explicit units."""
    device_class, state_class, unit, category, enabled = map_unit_to_sensor_classes(
        None, "generationPower"
    )
    assert device_class == SensorDeviceClass.POWER
    assert unit == UnitOfPower.WATT
    assert enabled is True

    device_class, state_class, unit, category, enabled = map_unit_to_sensor_classes(
        None, "batterySOC"
    )
    assert device_class == SensorDeviceClass.BATTERY
    assert unit == PERCENTAGE

    device_class, state_class, unit, category, enabled = map_unit_to_sensor_classes(
        None, "lastUpdateTime"
    )
    assert device_class is None
    assert category is not None
    assert enabled is True


def test_parse_numeric_value() -> None:
    """Parse numeric API values."""
    assert parse_numeric_value("85") == 85
    assert parse_numeric_value("12.5") == 12.5
    assert parse_numeric_value("online") == "online"
    assert parse_numeric_value("") is None
    assert parse_numeric_value(None) is None
