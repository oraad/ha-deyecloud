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


def measure_point_translation_key(key: str) -> str:
    """Return translation key for a measure point."""
    return normalize_measure_key(key)


def map_unit_to_sensor_classes(
    unit: str | None,
    key: str,
) -> tuple[
    SensorDeviceClass | None,
    SensorStateClass | None,
    str | None,
    EntityCategory | None,
    bool,
]:
    """Map API unit/key to HA sensor metadata."""
    normalized_unit = (unit or "").strip()
    normalized_key = normalize_measure_key(key)
    entity_category: EntityCategory | None = None
    enabled_default = normalized_key not in {
        normalize_measure_key(item) for item in _DISABLED_BY_DEFAULT_KEYS
    }

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
        )
    if normalized_unit in {"Wh", "WH"}:
        return (
            SensorDeviceClass.ENERGY,
            SensorStateClass.TOTAL,
            UnitOfEnergy.WATT_HOUR,
            entity_category,
            enabled_default,
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
        )
    if normalized_unit in {"V", "v"}:
        return (
            SensorDeviceClass.VOLTAGE,
            SensorStateClass.MEASUREMENT,
            UnitOfElectricPotential.VOLT,
            entity_category,
            enabled_default,
        )
    if normalized_unit in {"A", "a"}:
        return (
            SensorDeviceClass.CURRENT,
            SensorStateClass.MEASUREMENT,
            UnitOfElectricCurrent.AMPERE,
            entity_category,
            enabled_default,
        )
    if normalized_unit in {"%", PERCENTAGE} or "soc" in normalized_key:
        return (
            SensorDeviceClass.BATTERY,
            SensorStateClass.MEASUREMENT,
            PERCENTAGE,
            entity_category,
            enabled_default,
        )
    if normalized_unit in {"C", "°C", "℃"}:
        return (
            SensorDeviceClass.TEMPERATURE,
            SensorStateClass.MEASUREMENT,
            UnitOfTemperature.CELSIUS,
            entity_category,
            enabled_default,
        )
    if normalized_unit in {"Hz", "HZ"}:
        return (
            SensorDeviceClass.FREQUENCY,
            SensorStateClass.MEASUREMENT,
            UnitOfFrequency.HERTZ,
            entity_category,
            enabled_default,
        )

    return None, None, normalized_unit or None, entity_category, enabled_default


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
