"""Config flow for DeyeCloud."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlowWithReload,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.loader import async_get_loaded_integration

from .api import DeyeCloudApiClient
from .api_types import Station
from .const import (
    BASE_URL_OPTIONS,
    CONF_APP_ID,
    CONF_APP_SECRET,
    CONF_BASE_URL,
    CONF_COMPANY_ID,
    CONF_PASSWORD,
    CONF_SELECTED_STATIONS,
    CONF_STATION_ID,
    CONF_USERNAME,
    DEFAULT_BASE_URL_EU,
    DOMAIN,
    ISSUE_AUTH_FAILED,
    LOGGER,
    SUBENTRY_TYPE_STATION,
)
from .exceptions import (
    DeyeCloudAuthError,
    DeyeCloudConnectionError,
    DeyeCloudError,
    DeyeCloudNoStationsError,
)
from .subentry_sync import get_selected_station_ids, station_display_name

if TYPE_CHECKING:
    from .data import DeyeCloudConfigEntry


def _select_options(options: dict[str, str]) -> list[dict[str, str]]:
    """Build SelectSelector options for Home Assistant 2026.3+."""
    return [{"value": value, "label": label} for value, label in options.items()]


def _data_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_APP_ID): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required(CONF_APP_SECRET): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL_EU): SelectSelector(
                SelectSelectorConfig(
                    options=_select_options(BASE_URL_OPTIONS),
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_COMPANY_ID): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
        }
    )


def _normalize_user_input(user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    for key in (
        CONF_USERNAME,
        CONF_PASSWORD,
        CONF_APP_ID,
        CONF_APP_SECRET,
        CONF_BASE_URL,
        CONF_COMPANY_ID,
    ):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].strip()
    if not data.get(CONF_COMPANY_ID):
        data.pop(CONF_COMPANY_ID, None)
    return data


def _build_client(hass, user_input: dict[str, Any]) -> DeyeCloudApiClient:
    return DeyeCloudApiClient(
        session=async_get_clientsession(hass),
        base_url=user_input[CONF_BASE_URL],
        app_id=user_input[CONF_APP_ID],
        app_secret=user_input[CONF_APP_SECRET],
        username=user_input[CONF_USERNAME],
        password=user_input[CONF_PASSWORD],
        company_id=user_input.get(CONF_COMPANY_ID),
    )


async def _async_fetch_stations(hass, user_input: dict[str, Any]) -> list[Station]:
    client = _build_client(hass, user_input)
    return await client.async_get_stations()


async def _async_validate_account(hass, user_input: dict[str, Any]) -> list[Station]:
    stations = await _async_fetch_stations(hass, user_input)
    if not stations:
        raise DeyeCloudNoStationsError
    return stations


def _station_select_schema(
    stations: list[Station],
    *,
    default: list[str] | None = None,
) -> vol.Schema:
    options = {
        station.station_id: station_display_name(station, station.station_id)
        for station in stations
    }
    selected_default = default if default is not None else list(options.keys())
    return vol.Schema(
        {
            vol.Required(
                CONF_SELECTED_STATIONS,
                default=selected_default,
            ): SelectSelector(
                SelectSelectorConfig(
                    options=_select_options(options),
                    mode=SelectSelectorMode.LIST,
                    multiple=True,
                )
            ),
        }
    )


def _normalize_selected_stations(selected: list[str]) -> list[str]:
    return sorted({str(station_id) for station_id in selected if station_id})


class DeyeCloudConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DeyeCloud."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize config flow state."""
        self._flow_user_input: dict[str, Any] | None = None
        self._flow_stations: list[Station] = []

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: DeyeCloudConfigEntry,
    ) -> DeyeCloudOptionsFlowHandler:
        return DeyeCloudOptionsFlowHandler()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls,
        config_entry: DeyeCloudConfigEntry,
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_TYPE_STATION: StationSubentryFlowHandler}

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = _normalize_user_input(user_input)
            unique_id = (
                f"{user_input[CONF_USERNAME]}:"
                f"{user_input.get(CONF_COMPANY_ID) or 'personal'}"
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            try:
                stations = await _async_validate_account(self.hass, user_input)
            except DeyeCloudNoStationsError:
                errors["base"] = "no_stations_found"
            except DeyeCloudAuthError:
                errors["base"] = "auth_failed"
            except DeyeCloudConnectionError:
                errors["base"] = "cannot_connect"
            except DeyeCloudError:
                errors["base"] = "unknown"
            else:
                self._flow_user_input = user_input
                self._flow_stations = stations
                if len(stations) == 1:
                    return self.async_create_entry(
                        title=f"DeyeCloud - {user_input[CONF_USERNAME]}",
                        data=user_input,
                        options={
                            CONF_SELECTED_STATIONS: [stations[0].station_id],
                        },
                    )
                return await self.async_step_station_select()

        integration = async_get_loaded_integration(self.hass, DOMAIN)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _data_schema(),
                user_input,
            ),
            errors=errors,
            description_placeholders={
                "documentation_url": integration.documentation or "",
            },
        )

    async def async_step_station_select(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Let the user choose which stations to load."""
        if self._flow_user_input is None:
            return self.async_abort(reason="unknown")

        errors: dict[str, str] = {}
        if user_input is not None:
            selected = _normalize_selected_stations(user_input[CONF_SELECTED_STATIONS])
            valid_ids = {station.station_id for station in self._flow_stations}
            if not selected:
                errors["base"] = "no_stations_selected"
            elif any(station_id not in valid_ids for station_id in selected):
                errors["base"] = "station_not_found"
            else:
                return self.async_create_entry(
                    title=f"DeyeCloud - {self._flow_user_input[CONF_USERNAME]}",
                    data=self._flow_user_input,
                    options={CONF_SELECTED_STATIONS: selected},
                )

        return self.async_show_form(
            step_id="station_select",
            data_schema=_station_select_schema(self._flow_stations),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],
    ) -> ConfigFlowResult:
        """Handle reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Confirm reauthentication."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            user_input = _normalize_user_input({**reauth_entry.data, **user_input})
            try:
                await _async_validate_account(self.hass, user_input)
            except DeyeCloudNoStationsError:
                errors["base"] = "no_stations_found"
            except DeyeCloudAuthError:
                errors["base"] = "auth_failed"
            except DeyeCloudConnectionError:
                errors["base"] = "cannot_connect"
            except DeyeCloudError:
                errors["base"] = "unknown"
            else:
                ir.async_delete_issue(self.hass, DOMAIN, ISSUE_AUTH_FAILED)
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                _data_schema(),
                reauth_entry.data,
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            user_input = _normalize_user_input(user_input)
            try:
                await _async_validate_account(self.hass, user_input)
            except DeyeCloudNoStationsError:
                errors["base"] = "no_stations_found"
            except DeyeCloudAuthError:
                errors["base"] = "auth_failed"
            except DeyeCloudConnectionError:
                errors["base"] = "cannot_connect"
            except DeyeCloudError:
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=user_input,
                    title=f"DeyeCloud - {user_input[CONF_USERNAME]}",
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _data_schema(),
                entry.data,
            ),
            errors=errors,
        )


class StationSubentryFlowHandler(ConfigSubentryFlow):
    """Handle manual station subentry management."""

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> SubentryFlowResult:
        entry = self._get_entry()
        errors: dict[str, str] = {}
        configured_station_ids = {
            str(subentry.data.get(CONF_STATION_ID))
            for subentry in entry.subentries.values()
            if subentry.subentry_type == SUBENTRY_TYPE_STATION
            and subentry.data.get(CONF_STATION_ID)
        }

        try:
            client = _build_client(self.hass, dict(entry.data))
            stations = await client.async_get_stations()
        except DeyeCloudAuthError:
            errors["base"] = "auth_failed"
            stations = []
        except DeyeCloudConnectionError:
            errors["base"] = "cannot_connect"
            stations = []
        except DeyeCloudError:
            errors["base"] = "unknown"
            stations = []

        available: dict[str, str] = {}
        selected = get_selected_station_ids(entry)
        for station in stations:
            station_id = station.station_id
            if selected is not None and station_id not in selected:
                continue
            if station_id not in configured_station_ids:
                available[station_id] = station_display_name(station, station_id)

        if user_input is not None:
            station_id = user_input[CONF_STATION_ID]
            station = next(
                (item for item in stations if item.station_id == station_id),
                None,
            )
            if station is None:
                errors["base"] = "station_not_found"
            else:
                return self.async_create_entry(
                    title=station_display_name(station, station_id),
                    data={CONF_STATION_ID: station_id},
                    unique_id=station_id,
                )

        if not errors and not available:
            return self.async_abort(reason="all_stations_configured")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): SelectSelector(
                        SelectSelectorConfig(options=_select_options(available))
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> SubentryFlowResult:
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        station_id = str(subentry.data.get(CONF_STATION_ID, ""))

        try:
            client = _build_client(self.hass, dict(entry.data))
            stations = await client.async_get_stations()
        except DeyeCloudError as exc:
            LOGGER.warning("Station reconfigure failed: %s", exc)
            return self.async_abort(reason="auth_failed")

        station = next(
            (item for item in stations if item.station_id == station_id), None
        )
        if station is None:
            return self.async_abort(reason="station_not_found")

        return self.async_update_and_abort(
            entry,
            subentry,
            data={CONF_STATION_ID: station_id},
            title=station_display_name(station, station_id),
        )


class DeyeCloudOptionsFlowHandler(OptionsFlowWithReload):
    """Handle DeyeCloud options."""

    async def async_step_init(
        self,
        user_input: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        if user_input is not None:
            if user_input["next_step_id"] == "credentials":
                return await self.async_step_credentials()
            if user_input["next_step_id"] == "stations":
                return await self.async_step_stations()
        return self.async_show_menu(
            step_id="init",
            menu_options=["stations", "credentials"],
        )

    async def async_step_stations(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Update which stations are loaded."""
        errors: dict[str, str] = {}

        try:
            stations = await _async_fetch_stations(
                self.hass, dict(self.config_entry.data)
            )
        except DeyeCloudAuthError:
            errors["base"] = "auth_failed"
            stations = []
        except DeyeCloudConnectionError:
            errors["base"] = "cannot_connect"
            stations = []
        except DeyeCloudError:
            errors["base"] = "unknown"
            stations = []

        if user_input is not None:
            selected = _normalize_selected_stations(user_input[CONF_SELECTED_STATIONS])
            valid_ids = {station.station_id for station in stations}
            if not selected:
                errors["base"] = "no_stations_selected"
            elif any(station_id not in valid_ids for station_id in selected):
                errors["base"] = "station_not_found"
            else:
                return self.async_create_entry(
                    data={
                        **dict(self.config_entry.options),
                        CONF_SELECTED_STATIONS: selected,
                    }
                )

        current: list[str]
        selected = get_selected_station_ids(self.config_entry)
        if selected is None:
            current = [station.station_id for station in stations]
        else:
            current = sorted(selected)

        return self.async_show_form(
            step_id="stations",
            data_schema=_station_select_schema(stations, default=current),
            errors=errors,
        )

    async def async_step_credentials(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = _normalize_user_input(user_input)
            try:
                await _async_validate_account(self.hass, user_input)
            except DeyeCloudNoStationsError:
                errors["base"] = "no_stations_found"
            except DeyeCloudAuthError:
                errors["base"] = "auth_failed"
            except DeyeCloudConnectionError:
                errors["base"] = "cannot_connect"
            except DeyeCloudError:
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    title=f"DeyeCloud - {user_input[CONF_USERNAME]}",
                    data=user_input,
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="credentials",
            data_schema=self.add_suggested_values_to_schema(
                _data_schema(),
                dict(entry.data),
            ),
            errors=errors,
        )
