"""Constants for the DeyeCloud integration."""

from __future__ import annotations

import logging

DOMAIN = "deyecloud"
LOGGER = logging.getLogger(__package__)

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_APP_ID = "app_id"
CONF_APP_SECRET = "app_secret"
CONF_BASE_URL = "base_url"
CONF_COMPANY_ID = "company_id"
CONF_STATION_ID = "station_id"
CONF_SELECTED_STATIONS = "selected_stations"

SUBENTRY_TYPE_STATION = "station"

DEFAULT_BASE_URL_EU = "https://eu1-developer.deyecloud.com/v1.0"
DEFAULT_BASE_URL_US = "https://us1-developer.deyecloud.com/v1.0"
DEFAULT_BASE_URL_IN = "https://india-developer.deyecloud.com/v1.0"

BASE_URL_OPTIONS = {
    DEFAULT_BASE_URL_EU: "Europe / Asia-Pacific",
    DEFAULT_BASE_URL_US: "Americas",
    DEFAULT_BASE_URL_IN: "India",
}

DEVICE_TYPE_INVERTER = "INVERTER"
DEVICE_TYPE_MICRO_INVERTER = "MICRO_INVERTER"
DEVICE_TYPE_COLLECTOR = "COLLECTOR"
DEVICE_TYPE_BATTERY = "BATTERY"
DEVICE_TYPE_MECD = "MECD"
DEVICE_TYPE_METER = "METER"
DEVICE_TYPE_RELAY_BOX = "RELAY_BOX"
DEVICE_TYPE_OPTIMIZER = "OPTIMIZER"
DEVICE_TYPE_PV_MODULE = "PV_MODULE"
DEVICE_TYPE_OPTIMIZER_CONCENTRATOR = "OPTIMIZER_CONCENTRATOR"

KNOWN_DEVICE_TYPES = frozenset(
    {
        DEVICE_TYPE_INVERTER,
        DEVICE_TYPE_MICRO_INVERTER,
        DEVICE_TYPE_COLLECTOR,
        DEVICE_TYPE_BATTERY,
        DEVICE_TYPE_MECD,
        DEVICE_TYPE_METER,
        DEVICE_TYPE_RELAY_BOX,
        DEVICE_TYPE_OPTIMIZER,
        DEVICE_TYPE_PV_MODULE,
        DEVICE_TYPE_OPTIMIZER_CONCENTRATOR,
    }
)

# Panel optimizers report production only through /device/history. The
# concentrator itself carries no telemetry, and COLLECTOR is a pure data logger.
OPTIMIZER_DEVICE_TYPES = frozenset(
    {
        DEVICE_TYPE_OPTIMIZER,
        DEVICE_TYPE_OPTIMIZER_CONCENTRATOR,
    }
)

# Only the per-panel optimizers expose a per-device Production series.
PANEL_OPTIMIZER_DEVICE_TYPES = frozenset({DEVICE_TYPE_OPTIMIZER})

# Device types that always return an empty deviceDataList from /device/latest.
# They are dropped from the latest batches so they cannot consume the
# 10-serial-per-request budget or the API quota.
TELEMETRY_LESS_DEVICE_TYPES = frozenset(
    {
        DEVICE_TYPE_COLLECTOR,
        DEVICE_TYPE_OPTIMIZER,
        DEVICE_TYPE_OPTIMIZER_CONCENTRATOR,
    }
)

DEVICE_TYPE_LABELS: dict[str, str] = {
    DEVICE_TYPE_INVERTER: "Inverter",
    DEVICE_TYPE_MICRO_INVERTER: "Micro Inverter",
    DEVICE_TYPE_COLLECTOR: "Collector",
    DEVICE_TYPE_BATTERY: "Battery",
    DEVICE_TYPE_MECD: "MECD",
    DEVICE_TYPE_METER: "Meter",
    DEVICE_TYPE_RELAY_BOX: "Relay Box",
    DEVICE_TYPE_OPTIMIZER: "Optimizer",
    DEVICE_TYPE_PV_MODULE: "PV Module",
    DEVICE_TYPE_OPTIMIZER_CONCENTRATOR: "Optimizer Concentrator",
}

DEVICE_LATEST_BATCH_SIZE = 10
UPDATE_INTERVAL_SECONDS = 180
STALE_DEVICE_MISSING_POLLS = 3

# /device/history for optimizers only moves at the daily rollup level, so it is
# polled far less often than live telemetry.
OPTIMIZER_UPDATE_INTERVAL_SECONDS = 900
# A production series that has not moved for this long is treated as idle.
OPTIMIZER_IDLE_SECONDS = 3600
# History granularity sent to /device/history. These values are not documented
# in the OpenAPI schema; they were confirmed against a live SUN-XL20-B station.
HISTORY_GRANULARITY_DAILY = 2
HISTORY_GRANULARITY_MONTHLY = 3

ISSUE_AUTH_FAILED = "auth_failed"
ISSUE_API_UNAVAILABLE = "api_unavailable"

PARALLEL_UPDATES = 1


def device_type_label(device_type: str | None) -> str:
    """Return a friendly label for a DeyeCloud deviceType."""
    if not device_type:
        return "Device"
    if device_type in DEVICE_TYPE_LABELS:
        return DEVICE_TYPE_LABELS[device_type]
    return device_type.replace("_", " ").title()


def is_optimizer_device(device_type: str | None) -> bool:
    """Return True for optimizers and their concentrator."""
    return device_type in OPTIMIZER_DEVICE_TYPES


def is_panel_optimizer(device_type: str | None) -> bool:
    """Return True for optimizers that report a per-device Production series."""
    return device_type in PANEL_OPTIMIZER_DEVICE_TYPES


def supports_latest_telemetry(device_type: str | None) -> bool:
    """
    Return True when a device type can produce /device/latest data.

    An unknown device type is assumed to support telemetry so that new Deye
    device models keep working until they are verified.
    """
    if not device_type:
        return True
    return device_type not in TELEMETRY_LESS_DEVICE_TYPES
