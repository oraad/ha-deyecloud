"""Edge-case tests for the DeyeCloud API client."""

from __future__ import annotations

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.deyecloud.api import (
    DeyeCloudApiClient,
    _build_login_payload,
    _parse_device,
    _parse_station,
)
from custom_components.deyecloud.const import DEFAULT_BASE_URL_EU
from custom_components.deyecloud.exceptions import (
    DeyeCloudApiError,
    DeyeCloudAuthError,
)
from tests.conftest import load_fixture


@pytest.fixture
async def session() -> aiohttp.ClientSession:
    """Return aiohttp session."""
    async with aiohttp.ClientSession() as client_session:
        yield client_session


@pytest.fixture
async def client(session: aiohttp.ClientSession) -> DeyeCloudApiClient:
    """Return API client."""
    return DeyeCloudApiClient(
        session=session,
        base_url=DEFAULT_BASE_URL_EU,
        app_id="app-id",
        app_secret="app-secret",
        username="plainuser",
        password="secret",
    )


def test_build_login_payload_username() -> None:
    """Use username field when login is not an email."""
    assert _build_login_payload("plainuser") == {"username": "plainuser"}


def test_parse_station_and_device_skips_invalid() -> None:
    """Skip records missing required identifiers."""
    assert _parse_station({}) is None
    assert _parse_device({}, "101") is None


async def test_authenticate_with_company_id(client: DeyeCloudApiClient) -> None:
    """Include company id in token request when configured."""
    client._company_id = "42"
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        await client.async_authenticate()
        assert client.access_token == "test-access-token"


async def test_authenticate_token_failure(client: DeyeCloudApiClient) -> None:
    """Raise auth error when token response reports failure."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload={"success": False, "msg": "bad credentials"},
        )
        with pytest.raises(DeyeCloudAuthError, match="bad credentials"):
            await client.async_authenticate()


async def test_authenticate_missing_token(client: DeyeCloudApiClient) -> None:
    """Raise auth error when accessToken is missing."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload={"success": True},
        )
        with pytest.raises(DeyeCloudAuthError, match="missing accessToken"):
            await client.async_authenticate()


async def test_authenticate_default_expiry(client: DeyeCloudApiClient) -> None:
    """Use default expiry when expiresIn is absent."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload={"success": True, "accessToken": "token"},
        )
        await client.async_authenticate()
        assert client.access_token == "token"


async def test_get_stations_pagination_by_total(client: DeyeCloudApiClient) -> None:
    """Stop paginating when total count is reached."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/station/list",
            payload={
                "stationList": [{"id": "101", "name": "Home"}],
                "total": 1,
            },
        )
        stations = await client.async_get_stations()
        assert len(stations) == 1


async def test_get_station_devices_empty_and_fallback(
    client: DeyeCloudApiClient,
) -> None:
    """Handle empty station ids and infer station id for single-station calls."""
    assert await client.async_get_station_devices([]) == []

    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/station/device",
            payload={
                "deviceListItems": [
                    "invalid",
                    {"deviceSn": "INV999", "deviceType": "INVERTER"},
                ],
                "total": 1,
            },
        )
        devices = await client.async_get_station_devices(["101"])
        assert devices[0].device_sn == "INV999"


async def test_get_station_devices_invalid_station_id(
    client: DeyeCloudApiClient,
) -> None:
    """Skip invalid station ids when building numeric request ids."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/station/device",
            payload={"deviceListItems": [], "total": 0},
        )
        devices = await client.async_get_station_devices(["", "101"])
        assert devices == []


async def test_get_device_latest_empty(client: DeyeCloudApiClient) -> None:
    """Return empty list when no device serials are requested."""
    assert await client.async_get_device_latest([]) == []


async def test_get_station_latest_invalid_id(client: DeyeCloudApiClient) -> None:
    """Raise API error for invalid station ids."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        with pytest.raises(DeyeCloudApiError, match="Invalid station id"):
            await client.async_get_station_latest("")


async def test_get_station_latest_non_dict_payload(
    client: DeyeCloudApiClient,
) -> None:
    """Return empty station data when API payload is not a dict."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/station/latest",
            payload={"stationData": "invalid"},
        )
        latest = await client.async_get_station_latest("101")
        assert latest.data == {}


async def test_post_json_non_object_response(client: DeyeCloudApiClient) -> None:
    """Raise API error when response JSON is not an object."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=["not", "a", "dict"],
        )
        with pytest.raises(DeyeCloudApiError, match="not a JSON object"):
            await client.async_authenticate()
