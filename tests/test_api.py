"""Tests for the DeyeCloud API client."""

from __future__ import annotations

from unittest.mock import MagicMock

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.deyecloud.api import DeyeCloudApiClient
from custom_components.deyecloud.const import DEFAULT_BASE_URL_EU
from custom_components.deyecloud.exceptions import (
    DeyeCloudApiError,
    DeyeCloudAuthError,
    DeyeCloudConnectionError,
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
        username="user@example.com",
        password="secret",
    )


async def test_authenticate_success(client: DeyeCloudApiClient) -> None:
    """Authenticate and cache token."""
    token_payload = load_fixture("token.json")
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=token_payload,
        )
        await client.async_authenticate()
        assert client.access_token == "test-access-token"


async def test_get_stations_paginated(client: DeyeCloudApiClient) -> None:
    """Fetch stations from API."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/station/list",
            payload=load_fixture("stations.json"),
        )
        stations = await client.async_get_stations()
        assert [station.station_id for station in stations] == ["101", "202"]


async def test_get_station_devices(client: DeyeCloudApiClient) -> None:
    """Fetch devices for stations."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/station/device",
            payload=load_fixture("devices.json"),
        )
        devices = await client.async_get_station_devices(["101"])
        assert devices[0].device_sn == "INV123"


async def test_get_device_measure_points(client: DeyeCloudApiClient) -> None:
    """Fetch measure points for a device."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/device/measurePoints",
            payload=load_fixture("measure_points.json"),
        )
        points = await client.async_get_device_measure_points("INV123")
        assert points[0].key == "SOC"


async def test_get_device_latest_batches(client: DeyeCloudApiClient) -> None:
    """Fetch latest telemetry in batches."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/device/latest",
            payload=load_fixture("device_latest.json"),
        )
        latest = await client.async_get_device_latest(["INV123"])
        assert latest[0].data_list[0].value == "85"


async def test_get_station_latest(client: DeyeCloudApiClient) -> None:
    """Fetch station latest data."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/station/latest",
            payload=load_fixture("station_latest.json"),
        )
        latest = await client.async_get_station_latest("101")
        assert latest.data["generationValue"] == 12.5


async def test_auth_error_raises(client: DeyeCloudApiClient) -> None:
    """Raise auth error on 401."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            status=401,
        )
        with pytest.raises(DeyeCloudAuthError):
            await client.async_authenticate()


async def test_authorized_post_retries_after_401(client: DeyeCloudApiClient) -> None:
    """Re-authenticate and retry once when an authorized call returns 401."""
    token_payload = load_fixture("token.json")
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=token_payload,
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/station/list",
            status=401,
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=token_payload,
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/station/list",
            payload=load_fixture("stations.json"),
        )
        stations = await client.async_get_stations()
        assert [station.station_id for station in stations] == ["101", "202"]


async def test_api_error_on_success_false(client: DeyeCloudApiClient) -> None:
    """Raise API error when success is false."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/station/list",
            payload={"success": False, "msg": "failed"},
        )
        with pytest.raises(DeyeCloudApiError):
            await client.async_get_stations()


async def test_connection_error(client: DeyeCloudApiClient) -> None:
    """Raise connection error on network failure."""
    mock_session = MagicMock()
    mock_session.post = MagicMock(side_effect=aiohttp.ClientError("boom"))
    client._session = mock_session
    with pytest.raises(DeyeCloudConnectionError):
        await client._post_json(f"{DEFAULT_BASE_URL_EU}/station/list")


async def test_authorized_post_force_reauth_with_valid_cached_token(
    client: DeyeCloudApiClient,
) -> None:
    """401 retry clears a still-valid cached token and fetches a new one."""
    import time

    token_payload = load_fixture("token.json")
    client._access_token = "stale-token"
    client._token_expires_at = time.monotonic() + 3600

    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/station/list",
            status=401,
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=token_payload,
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/station/list",
            payload=load_fixture("stations.json"),
        )
        stations = await client.async_get_stations()
        assert client.access_token == "test-access-token"
        assert [station.station_id for station in stations] == ["101", "202"]


async def test_get_device_latest_multiple_batches(client: DeyeCloudApiClient) -> None:
    """Fetch latest telemetry in more than one API batch."""
    device_sns = [f"INV{i:03d}" for i in range(11)]
    latest_payload = load_fixture("device_latest.json")

    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/device/latest",
            payload=latest_payload,
            repeat=True,
        )
        latest = await client.async_get_device_latest(device_sns)
        assert len(latest) == 2
