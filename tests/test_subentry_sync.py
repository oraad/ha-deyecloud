"""Tests for plant subentry sync."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.deyecloud.api_types import Station
from custom_components.deyecloud.const import (
    CONF_SELECTED_PLANTS,
    CONF_STATION_ID,
    DOMAIN,
    SUBENTRY_TYPE_PLANT,
)
from custom_components.deyecloud.subentry_sync import (
    async_sync_plant_subentries,
    build_plant_subentry_map,
    filter_stations_by_selection,
    get_selected_station_ids,
    get_station_id,
    normalize_station_id,
    register_plant_entities,
    station_display_name,
)


def test_normalize_station_id() -> None:
    """Normalize station ids."""
    assert normalize_station_id(101) == "101"
    assert normalize_station_id(101.0) == "101"
    assert normalize_station_id("101.0") == "101"
    assert normalize_station_id(None) is None
    assert normalize_station_id("") is None


def test_get_station_id_from_station_model() -> None:
    """Extract station id from Station model."""
    assert get_station_id(Station("303", "Plant")) == "303"


def test_get_station_id_from_dict() -> None:
    """Extract station id from API dict."""
    assert get_station_id({"id": 101}) == "101"
    assert get_station_id({"stationId": 202}) == "202"


def test_station_display_name() -> None:
    """Return display name."""
    assert station_display_name({"name": "Home"}, "101") == "Home"
    assert station_display_name(Station("101", "Plant A"), "101") == "Plant A"


async def test_sync_adds_plant_subentries(hass, config_data) -> None:
    """Sync creates subentries for API stations."""
    entry = MockConfigEntry(domain=DOMAIN, data=config_data)
    entry.add_to_hass(hass)
    stations = [
        Station(station_id="101", name="Home Plant"),
        Station(station_id="202", name="Office Plant"),
    ]

    _, structural_changed, _ = await async_sync_plant_subentries(hass, entry, stations)
    assert structural_changed is True

    refreshed = hass.config_entries.async_get_entry(entry.entry_id)
    assert refreshed is not None
    assert len(refreshed.subentries) == 2
    plant_map = build_plant_subentry_map(refreshed)
    assert set(plant_map) == {"101", "202"}


async def test_sync_respects_selected_plants(hass, mock_config_entry) -> None:
    """Sync only creates subentries for selected plants."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={CONF_SELECTED_PLANTS: ["101"]},
    )
    entry = hass.config_entries.async_get_entry(mock_config_entry.entry_id)
    assert entry is not None

    _, structural_changed, _ = await async_sync_plant_subentries(
        hass,
        entry,
        [
            Station(station_id="101", name="Home Plant"),
            Station(station_id="202", name="Office Plant"),
        ],
    )
    assert structural_changed is True
    refreshed = hass.config_entries.async_get_entry(mock_config_entry.entry_id)
    assert refreshed is not None
    assert set(build_plant_subentry_map(refreshed)) == {"101"}


def test_filter_stations_by_selection(config_data) -> None:
    """Filter API stations using entry options."""
    stations = [
        Station(station_id="101", name="Home Plant"),
        Station(station_id="202", name="Office Plant"),
    ]
    entry_all = MockConfigEntry(domain=DOMAIN, data=config_data)
    assert get_selected_station_ids(entry_all) is None
    assert len(filter_stations_by_selection(stations, entry_all)) == 2

    filtered_entry = MockConfigEntry(
        domain=DOMAIN,
        data=dict(config_data),
        options={CONF_SELECTED_PLANTS: ["202"]},
    )
    filtered = filter_stations_by_selection(stations, filtered_entry)
    assert len(filtered) == 1
    assert filtered[0].station_id == "202"


async def test_sync_removes_stale_subentry(hass, mock_config_entry) -> None:
    """Sync removes subentries no longer returned by API."""
    mock_config_entry.add_to_hass(hass)
    entry = hass.config_entries.async_get_entry(mock_config_entry.entry_id)
    assert entry is not None
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={CONF_STATION_ID: "999"},
            subentry_type=SUBENTRY_TYPE_PLANT,
            title="Stale",
            unique_id="999",
        ),
    )

    _, structural_changed, _ = await async_sync_plant_subentries(
        hass,
        entry,
        [Station(station_id="101", name="Home Plant")],
    )
    assert structural_changed is True
    refreshed = hass.config_entries.async_get_entry(mock_config_entry.entry_id)
    assert refreshed is not None
    assert len(refreshed.subentries) == 1


async def test_sync_updates_subentry_title(hass, config_data) -> None:
    """Sync updates plant subentry titles when station names change."""
    entry = MockConfigEntry(domain=DOMAIN, data=config_data)
    entry.add_to_hass(hass)
    current = hass.config_entries.async_get_entry(entry.entry_id)
    assert current is not None
    hass.config_entries.async_add_subentry(
        current,
        ConfigSubentry(
            data={CONF_STATION_ID: "101"},
            subentry_type=SUBENTRY_TYPE_PLANT,
            title="Old Plant Name",
            unique_id="101",
        ),
    )

    _, structural_changed, metadata_changed = await async_sync_plant_subentries(
        hass,
        current,
        [Station(station_id="101", name="Home Plant")],
    )
    assert structural_changed is False
    assert metadata_changed is True
    refreshed = hass.config_entries.async_get_entry(entry.entry_id)
    assert refreshed is not None
    assert refreshed.subentries[next(iter(refreshed.subentries))].title == "Home Plant"


def test_register_plant_entities() -> None:
    """Register entities against subentries."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.subentries = {
        "sub-101": ConfigSubentry(
            data={CONF_STATION_ID: "101"},
            subentry_id="sub-101",
            subentry_type=SUBENTRY_TYPE_PLANT,
            title="Home",
            unique_id="101",
        )
    }
    added: list[tuple[list, str | None]] = []

    def async_add_entities(entities, config_subentry_id=None):
        added.append((entities, config_subentry_id))

    count = register_plant_entities(
        entry=entry,
        coordinator_data={"101": object()},
        async_add_entities=async_add_entities,
        build_fn=lambda station_id, data, subentry_id: ["entity"],
    )
    assert count == 1
    assert added[0][1] == "sub-101"


def test_register_plant_entities_without_subentries(caplog) -> None:
    """Log error when coordinator data exists but no plant subentries are configured."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    count = register_plant_entities(
        entry=entry,
        coordinator_data={"101": object()},
        async_add_entities=lambda *args, **kwargs: None,
        build_fn=lambda station_id, data, subentry_id: [],
    )
    assert count == 0
    assert "No plant subentries configured" in caplog.text


def test_register_plant_entities_missing_subentry(caplog) -> None:
    """Warn when coordinator data references an unknown plant subentry."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.subentries = {
        "sub-101": ConfigSubentry(
            data={CONF_STATION_ID: "101"},
            subentry_id="sub-101",
            subentry_type=SUBENTRY_TYPE_PLANT,
            title="Home",
            unique_id="101",
        )
    }
    count = register_plant_entities(
        entry=entry,
        coordinator_data={"202": object()},
        async_add_entities=lambda *args, **kwargs: None,
        build_fn=lambda station_id, data, subentry_id: ["entity"],
    )
    assert count == 0
    assert "No plant subentry for station 202" in caplog.text


def test_build_plant_subentry_map_skips_non_plants() -> None:
    """Only plant subentries are included in the plant map."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.subentries = {
        "other": ConfigSubentry(
            data={CONF_STATION_ID: "999"},
            subentry_id="other",
            subentry_type="other",
            title="Other",
            unique_id="999",
        )
    }
    assert build_plant_subentry_map(entry) == {}
