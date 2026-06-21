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

BASE_URL_OPTIONS = {
    DEFAULT_BASE_URL_EU: "Europe / Asia-Pacific",
    DEFAULT_BASE_URL_US: "Americas",
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
}

DEVICE_LATEST_BATCH_SIZE = 10
UPDATE_INTERVAL_SECONDS = 180
STALE_DEVICE_MISSING_POLLS = 3

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
