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


async def test_get_station_devices_deduplicates_rows(
    client: DeyeCloudApiClient,
) -> None:
    """Prefer typed device rows when the API returns duplicate serials."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/station/device",
            payload={
                "success": True,
                "deviceListItems": [
                    {
                        "deviceSn": "3422409399",
                        "deviceType": "COLLECTOR",
                        "stationId": 101,
                    },
                    {"deviceSn": "3422409399", "stationId": 101},
                ],
                "total": 2,
            },
        )
        devices = await client.async_get_station_devices(["101"])
        assert len(devices) == 1
        assert devices[0].device_sn == "3422409399"
        assert devices[0].device_type == "COLLECTOR"


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


async def test_get_device_measure_points_accepts_key_strings(
    client: DeyeCloudApiClient,
) -> None:
    """The documented measurePoints schema returns bare key strings."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/device/measurePoints",
            payload={
                "success": True,
                "measurePoints": ["SOC", "TotalChargeEnergy", "", None],
            },
        )
        points = await client.async_get_device_measure_points("INV123")
        assert [point.key for point in points] == ["SOC", "TotalChargeEnergy"]
        assert all(point.name is None and point.unit is None for point in points)


async def test_authenticate_strips_bearer_prefix(
    client: DeyeCloudApiClient,
) -> None:
    """Access tokens are documented with the scheme already applied."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload={
                "success": True,
                "accessToken": "Bearer eyJhbGciOiJSUzI1NiIsInR5cC",
                "tokenType": "bearer",
                "expiresIn": 5183999,
            },
        )
        await client.async_authenticate()
        assert client.access_token == "eyJhbGciOiJSUzI1NiIsInR5cC"


async def test_authenticate_sends_single_bearer_header(
    client: DeyeCloudApiClient,
) -> None:
    """A prefixed token must not produce a doubled Bearer header."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload={
                "success": True,
                "accessToken": "bearer abc123",
                "expiresIn": "3600",
            },
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/station/list",
            payload=load_fixture("stations.json"),
        )
        await client.async_get_stations()

        headers = [
            call.kwargs["headers"]
            for call_list in mocked.requests.values()
            for call in call_list
            if call.kwargs.get("headers")
        ]
        assert headers == [{"Authorization": "Bearer abc123"}]


@pytest.mark.parametrize(
    "expires_in",
    [3600, "3600", 3600.0, " 3600 "],
)
async def test_authenticate_accepts_expires_in_string(
    client: DeyeCloudApiClient,
    expires_in: object,
) -> None:
    """ExpiresIn is declared as a string in the OpenAPI schema."""
    import time

    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload={
                "success": True,
                "accessToken": "test-access-token",
                "expiresIn": expires_in,
            },
        )
        await client.async_authenticate()

    assert client._token_expires_at == pytest.approx(
        time.monotonic() + 3540,
        abs=5,
    )


@pytest.mark.parametrize("expires_in", [None, "not-a-number", -1, True])
async def test_authenticate_falls_back_on_bad_expires_in(
    client: DeyeCloudApiClient,
    expires_in: object,
) -> None:
    """Unusable expiresIn values fall back to the conservative 25 minute window."""
    import time

    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload={
                "success": True,
                "accessToken": "test-access-token",
                "expiresIn": expires_in,
            },
        )
        await client.async_authenticate()

    assert client._token_expires_at == pytest.approx(
        time.monotonic() + 25 * 60,
        abs=5,
    )


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
        assert latest.data["generationPower"] == 1500.0
        assert latest.data["batterySOC"] == 95.0
        assert "success" not in latest.data


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


def _history_request(mocked) -> dict:
    """Return the JSON body sent to /device/history."""
    key = next(
        key for key in mocked.requests if str(key[1]).endswith("/device/history")
    )
    # The client posts with json=, so aioresponses exposes the decoded body.
    return mocked.requests[key][0].kwargs["json"]


async def test_get_device_history_returns_production_buckets(
    client: DeyeCloudApiClient,
) -> None:
    """Fetch daily Production history for an optimizer."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/device/history",
            payload=load_fixture("optimizer_history.json"),
        )
        buckets = await client.async_get_device_history(
            "OPT123",
            granularity=2,
            start_at="2026-09-01",
            end_at="2026-09-28",
        )
        assert [bucket["time"] for bucket in buckets] == [
            "2026-09-26",
            "2026-09-27",
            "2026-09-28",
        ]
        assert buckets[-1]["itemList"] == [
            {"key": "Production", "value": "0.42", "unit": "kWh"}
        ]


async def test_get_device_history_sends_expected_payload(
    client: DeyeCloudApiClient,
) -> None:
    """History requests carry the granularity and inclusive date bounds."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/device/history",
            payload=load_fixture("optimizer_history.json"),
        )
        await client.async_get_device_history(
            "OPT123",
            granularity=2,
            start_at="2026-09-01",
            end_at="2026-09-28",
        )
        assert _history_request(mocked) == {
            "deviceSn": "OPT123",
            "granularity": 2,
            "startAt": "2026-09-01",
            "endAt": "2026-09-28",
        }


async def test_get_device_history_includes_measure_points_when_given(
    client: DeyeCloudApiClient,
) -> None:
    """An explicit measure point list is forwarded to the API."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/device/history",
            payload=load_fixture("optimizer_history.json"),
        )
        await client.async_get_device_history(
            "OPT123",
            granularity=2,
            start_at="2026-09-01",
            end_at="2026-09-28",
            measure_points=["Production"],
        )
        assert _history_request(mocked)["measurePoints"] == ["Production"]


async def test_get_device_history_empty_response(
    client: DeyeCloudApiClient,
) -> None:
    """An empty dataList yields no buckets rather than raising."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/device/history",
            payload=load_fixture("optimizer_history_empty.json"),
        )
        buckets = await client.async_get_device_history(
            "OPT123",
            granularity=2,
            start_at="2026-09-01",
            end_at="2026-09-28",
        )
        assert buckets == []


async def test_get_device_history_ignores_non_dict_entries(
    client: DeyeCloudApiClient,
) -> None:
    """Junk entries in dataList are dropped instead of breaking derivation."""
    with aioresponses() as mocked:
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/account/token?appId=app-id",
            payload=load_fixture("token.json"),
        )
        mocked.post(
            f"{DEFAULT_BASE_URL_EU}/device/history",
            payload={"dataList": ["nope", None, {"time": "2026-09-28"}]},
        )
        buckets = await client.async_get_device_history(
            "OPT123",
            granularity=2,
            start_at="2026-09-01",
            end_at="2026-09-28",
        )
        assert buckets == [{"time": "2026-09-28"}]


async def test_get_device_latest_skips_empty_list(client: DeyeCloudApiClient) -> None:
    """An empty serial list short-circuits instead of calling the API."""
    assert await client.async_get_device_latest([]) == []
