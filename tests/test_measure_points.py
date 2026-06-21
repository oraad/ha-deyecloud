"""Tests for measure point helpers."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower

from custom_components.deyecloud.measure_points import (
    friendly_measure_name,
    has_measure_point_translation,
    map_unit_to_sensor_classes,
    measure_point_translation_key,
    normalize_measure_key,
    parse_numeric_value,
    station_metric_label,
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


def test_station_metric_label() -> None:
    """Return friendly station metric labels."""
    assert station_metric_label("generationPower") == "Solar generation"
    assert station_metric_label("batterySOC") == "Battery SOC"


def test_has_measure_point_translation() -> None:
    """Detect measure points with defined translations."""
    assert has_measure_point_translation("SOC") is True
    assert has_measure_point_translation("Pv1Voltage") is False


def test_map_unit_to_sensor_classes_power_suffix_regressions() -> None:
    """Unit-based classification wins over _power key suffix."""
    device_class, _state_class, unit, _category, _enabled, precision = (
        map_unit_to_sensor_classes("kWh", "gridPower")
    )
    assert device_class == SensorDeviceClass.ENERGY
    assert unit == UnitOfEnergy.KILO_WATT_HOUR
    assert precision == 2

    device_class, _state_class, unit, _category, _enabled, precision = (
        map_unit_to_sensor_classes("V", "pv1_voltage")
    )
    assert device_class == SensorDeviceClass.VOLTAGE
    assert precision == 1

    device_class, _state_class, unit, _category, _enabled, precision = (
        map_unit_to_sensor_classes("W", "SOC")
    )
    assert device_class == SensorDeviceClass.BATTERY
    assert unit == PERCENTAGE
    assert precision == 0

    device_class, _state_class, unit, _category, _enabled, precision = (
        map_unit_to_sensor_classes(None, "TotalGridPower")
    )
    assert device_class == SensorDeviceClass.POWER
    assert unit == UnitOfPower.WATT
    assert precision == 0


def test_map_unit_to_sensor_classes() -> None:
    """Map units to HA classes."""
    device_class, state_class, unit, category, enabled, precision = (
        map_unit_to_sensor_classes("kWh", "generationValue")
    )
    assert device_class == SensorDeviceClass.ENERGY
    assert state_class == SensorStateClass.TOTAL
    assert unit == UnitOfEnergy.KILO_WATT_HOUR
    assert category is None
    assert enabled is True
    assert precision == 2

    device_class, state_class, unit, category, enabled, precision = (
        map_unit_to_sensor_classes("W", "TotalGridPower")
    )
    assert device_class == SensorDeviceClass.POWER
    assert unit == UnitOfPower.WATT
    assert precision == 0

    device_class, state_class, unit, category, enabled, precision = (
        map_unit_to_sensor_classes("%", "SOC")
    )
    assert device_class == SensorDeviceClass.BATTERY
    assert unit == PERCENTAGE
    assert precision == 0

    device_class, state_class, unit, category, enabled, precision = (
        map_unit_to_sensor_classes(None, "collectionTime")
    )
    assert enabled is False
    assert precision is None

    device_class, state_class, unit, category, enabled, precision = (
        map_unit_to_sensor_classes("Wh", "energy")
    )
    assert device_class == SensorDeviceClass.ENERGY
    assert unit == UnitOfEnergy.WATT_HOUR
    assert precision == 0

    device_class, state_class, unit, category, enabled, precision = (
        map_unit_to_sensor_classes("V", "voltage")
    )
    assert device_class == SensorDeviceClass.VOLTAGE
    assert precision == 1

    device_class, state_class, unit, category, enabled, precision = (
        map_unit_to_sensor_classes("A", "current")
    )
    assert device_class == SensorDeviceClass.CURRENT
    assert precision == 1

    device_class, state_class, unit, category, enabled, precision = (
        map_unit_to_sensor_classes("°C", "temperature")
    )
    assert device_class == SensorDeviceClass.TEMPERATURE
    assert precision == 1

    device_class, state_class, unit, category, enabled, precision = (
        map_unit_to_sensor_classes("Hz", "frequency")
    )
    assert device_class == SensorDeviceClass.FREQUENCY
    assert precision == 2

    device_class, state_class, unit, category, enabled, precision = (
        map_unit_to_sensor_classes("kW", "activePower")
    )
    assert device_class == SensorDeviceClass.POWER
    assert precision == 2

    device_class, state_class, unit, category, enabled, precision = (
        map_unit_to_sensor_classes(None, "device_state")
    )
    assert enabled is True
    assert category is not None
    assert precision is None


def test_map_unit_to_sensor_classes_station_metrics() -> None:
    """Map production station/latest keys without explicit units."""
    device_class, _state_class, unit, category, enabled, precision = (
        map_unit_to_sensor_classes(None, "generationPower")
    )
    assert device_class == SensorDeviceClass.POWER
    assert unit == UnitOfPower.WATT
    assert enabled is True
    assert precision == 0

    device_class, _state_class, unit, category, enabled, precision = (
        map_unit_to_sensor_classes(None, "batterySOC")
    )
    assert device_class == SensorDeviceClass.BATTERY
    assert unit == PERCENTAGE
    assert precision == 0

    device_class, _state_class, unit, category, enabled, precision = (
        map_unit_to_sensor_classes(None, "lastUpdateTime")
    )
    assert device_class is None
    assert category is not None
    assert enabled is True
    assert precision is None


def test_parse_numeric_value() -> None:
    """Parse numeric API values."""
    assert parse_numeric_value("85") == 85
    assert parse_numeric_value("12.5") == 12.5
    assert parse_numeric_value("online") == "online"
    assert parse_numeric_value("") is None
    assert parse_numeric_value(None) is None
