"""Measure point mapping helpers."""

from __future__ import annotations

import re

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import EntityCategory

_DISABLED_BY_DEFAULT_KEYS = frozenset(
    {
        "collectionTime",
        "DeviceTime",
        "UpdateTime",
        "SignalStrength",
        "RSSI",
        "RSRP",
        "RSRQ",
        "SINR",
        "IMEI",
        "ICCID",
        "FirmwareVersion",
        "HardwareVersion",
    }
)

_STATION_POWER_KEYS = frozenset(
    {
        "generationPower",
        "consumptionPower",
        "gridPower",
        "purchasePower",
        "chargePower",
        "dischargePower",
        "batteryPower",
        "wirePower",
    }
)

_STATION_METRIC_LABELS: dict[str, str] = {
    "generationPower": "Solar generation",
    "consumptionPower": "Consumption",
    "gridPower": "Grid power",
    "purchasePower": "Grid import",
    "chargePower": "Battery charge",
    "dischargePower": "Battery discharge",
    "batteryPower": "Battery power",
    "batterySOC": "Battery SOC",
    "wirePower": "Wire power",
    "lastUpdateTime": "Last update",
}

_TRANSLATED_MEASURE_POINT_KEYS = frozenset(
    {
        "soc",
        "total_grid_power",
        "battery_power",
        "generation_value",
        "consumption_value",
        "grid_value",
        "purchase_value",
        "charge_value",
        "discharge_value",
        "current_power",
        "grid_power",
        "buy_power",
        "sell_power",
    }
)


def normalize_measure_key(key: str) -> str:
    """Convert API measure keys to stable snake_case identifiers."""
    key = key.strip()
    key = re.sub(r"[^\w\s-]", "", key)
    key = re.sub(r"[\s-]+", "_", key)
    key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return key.lower().strip("_")


def friendly_measure_name(key: str, api_name: str | None = None) -> str:
    """Return a human-readable measure point name."""
    if api_name and api_name.strip():
        return api_name.strip()
    normalized = normalize_measure_key(key).replace("_", " ")
    return normalized.title()


def station_metric_label(key: str) -> str:
    """Return a human-readable station metric name."""
    return _STATION_METRIC_LABELS.get(key, friendly_measure_name(key))


def measure_point_translation_key(key: str) -> str:
    """Return translation key for a measure point."""
    return normalize_measure_key(key)


def has_measure_point_translation(key: str) -> bool:
    """Return True when strings.json defines a translation for this measure point."""
    return normalize_measure_key(key) in _TRANSLATED_MEASURE_POINT_KEYS


_UNIT_PRECISION: dict[str, int] = {
    "kWh": 2,
    "KWH": 2,
    "Wh": 0,
    "WH": 0,
    "%": 0,
    PERCENTAGE: 0,
    "V": 1,
    "v": 1,
    "A": 1,
    "a": 1,
    "C": 1,
    "°C": 1,
    "℃": 1,
    "Hz": 2,
    "HZ": 2,
    "kW": 2,
    "KW": 2,
    "W": 0,
}

_DEVICE_CLASS_PRECISION: dict[SensorDeviceClass, int] = {
    SensorDeviceClass.BATTERY: 0,
    SensorDeviceClass.POWER: 0,
    SensorDeviceClass.ENERGY: 2,
    SensorDeviceClass.VOLTAGE: 1,
    SensorDeviceClass.CURRENT: 1,
    SensorDeviceClass.TEMPERATURE: 1,
    SensorDeviceClass.FREQUENCY: 2,
}


def _display_precision(
    device_class: SensorDeviceClass | None,
    normalized_unit: str,
) -> int | None:
    """Return suggested UI decimal places for a sensor type."""
    if normalized_unit in _UNIT_PRECISION:
        return _UNIT_PRECISION[normalized_unit]
    if device_class is not None and device_class in _DEVICE_CLASS_PRECISION:
        return _DEVICE_CLASS_PRECISION[device_class]
    if normalized_unit:
        return 2
    return None


def map_unit_to_sensor_classes(
    unit: str | None,
    key: str,
) -> tuple[
    SensorDeviceClass | None,
    SensorStateClass | None,
    str | None,
    EntityCategory | None,
    bool,
    int | None,
]:
    """Map API unit/key to HA sensor metadata."""
    normalized_unit = (unit or "").strip()
    normalized_key = normalize_measure_key(key)
    entity_category: EntityCategory | None = None
    enabled_default = normalized_key not in {
        normalize_measure_key(item) for item in _DISABLED_BY_DEFAULT_KEYS
    }

    if key == "batterySOC" or normalized_key == "battery_soc":
        return (
            SensorDeviceClass.BATTERY,
            SensorStateClass.MEASUREMENT,
            PERCENTAGE,
            entity_category,
            enabled_default,
            _display_precision(SensorDeviceClass.BATTERY, normalized_unit),
        )
    if key == "lastUpdateTime" or normalized_key == "last_update_time":
        entity_category = EntityCategory.DIAGNOSTIC
        return (
            None,
            SensorStateClass.MEASUREMENT,
            None,
            entity_category,
            enabled_default,
            None,
        )

    if normalized_key in {"device_state", "connect_status", "online", "status"}:
        entity_category = EntityCategory.DIAGNOSTIC
        enabled_default = True

    if normalized_unit in {"kWh", "KWH"}:
        return (
            SensorDeviceClass.ENERGY,
            SensorStateClass.TOTAL,
            UnitOfEnergy.KILO_WATT_HOUR,
            entity_category,
            enabled_default,
            _display_precision(SensorDeviceClass.ENERGY, normalized_unit),
        )
    if normalized_unit in {"Wh", "WH"}:
        return (
            SensorDeviceClass.ENERGY,
            SensorStateClass.TOTAL,
            UnitOfEnergy.WATT_HOUR,
            entity_category,
            enabled_default,
            _display_precision(SensorDeviceClass.ENERGY, normalized_unit),
        )
    if normalized_unit in {"%", PERCENTAGE} or "soc" in normalized_key:
        return (
            SensorDeviceClass.BATTERY,
            SensorStateClass.MEASUREMENT,
            PERCENTAGE,
            entity_category,
            enabled_default,
            _display_precision(SensorDeviceClass.BATTERY, normalized_unit),
        )
    if normalized_unit in {"V", "v"}:
        return (
            SensorDeviceClass.VOLTAGE,
            SensorStateClass.MEASUREMENT,
            UnitOfElectricPotential.VOLT,
            entity_category,
            enabled_default,
            _display_precision(SensorDeviceClass.VOLTAGE, normalized_unit),
        )
    if normalized_unit in {"A", "a"}:
        return (
            SensorDeviceClass.CURRENT,
            SensorStateClass.MEASUREMENT,
            UnitOfElectricCurrent.AMPERE,
            entity_category,
            enabled_default,
            _display_precision(SensorDeviceClass.CURRENT, normalized_unit),
        )
    if normalized_unit in {"C", "°C", "℃"}:
        return (
            SensorDeviceClass.TEMPERATURE,
            SensorStateClass.MEASUREMENT,
            UnitOfTemperature.CELSIUS,
            entity_category,
            enabled_default,
            _display_precision(SensorDeviceClass.TEMPERATURE, normalized_unit),
        )
    if normalized_unit in {"Hz", "HZ"}:
        return (
            SensorDeviceClass.FREQUENCY,
            SensorStateClass.MEASUREMENT,
            UnitOfFrequency.HERTZ,
            entity_category,
            enabled_default,
            _display_precision(SensorDeviceClass.FREQUENCY, normalized_unit),
        )
    if normalized_unit in {"W", "kW", "KW"}:
        native_unit = (
            UnitOfPower.KILO_WATT
            if normalized_unit in {"kW", "KW"}
            else UnitOfPower.WATT
        )
        return (
            SensorDeviceClass.POWER,
            SensorStateClass.MEASUREMENT,
            native_unit,
            entity_category,
            enabled_default,
            _display_precision(SensorDeviceClass.POWER, normalized_unit),
        )

    if key in _STATION_POWER_KEYS or (
        normalized_key.endswith("_power") and not normalized_unit
    ):
        return (
            SensorDeviceClass.POWER,
            SensorStateClass.MEASUREMENT,
            UnitOfPower.WATT,
            entity_category,
            enabled_default,
            _display_precision(SensorDeviceClass.POWER, normalized_unit),
        )

    return (
        None,
        None,
        normalized_unit or None,
        entity_category,
        enabled_default,
        _display_precision(None, normalized_unit),
    )


def parse_numeric_value(value: str | None) -> float | int | str | None:
    """Parse API string values into numeric states when possible."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text
