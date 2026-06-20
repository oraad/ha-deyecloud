"""Async DeyeCloud OpenAPI client."""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

import aiohttp

from .api_types import (
    DataPoint,
    Device,
    DeviceData,
    MeasurePoint,
    Station,
    StationData,
)
from .const import DEVICE_LATEST_BATCH_SIZE
from .exceptions import (
    DeyeCloudApiError,
    DeyeCloudAuthError,
    DeyeCloudConnectionError,
)
from .subentry_sync import get_station_id, normalize_station_id


def _sha256(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest().lower()


def _build_login_payload(login: str) -> dict[str, str]:
    login = login.strip()
    if "@" in login:
        return {"email": login}
    return {"username": login}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _parse_station(raw: dict[str, Any]) -> Station | None:
    station_id = get_station_id(raw)
    if not station_id:
        return None
    name = raw.get("name") or raw.get("stationName") or f"Plant {station_id}"
    return Station(station_id=station_id, name=str(name), raw=raw)


_STATION_LATEST_METADATA_KEYS = frozenset(
    {"code", "msg", "success", "requestId"},
)


def _parse_station_latest_data(response: dict[str, Any]) -> dict[str, Any]:
    """Return station telemetry fields without API wrapper metadata."""
    data = response.get("stationData") or response
    if not isinstance(data, dict):
        return {}
    return {
        key: value
        for key, value in data.items()
        if key not in _STATION_LATEST_METADATA_KEYS
    }


def _prefer_device(existing: Device, new: Device) -> Device:
    """Keep the row with a known device type when the API returns duplicates."""
    if existing.device_type and not new.device_type:
        return existing
    if new.device_type and not existing.device_type:
        return new
    return existing


def _dedupe_devices(devices: list[Device]) -> list[Device]:
    """Drop duplicate deviceSn rows per station."""
    deduped: dict[tuple[str, str], Device] = {}
    for device in devices:
        key = (device.station_id, device.device_sn)
        if key in deduped:
            deduped[key] = _prefer_device(deduped[key], device)
        else:
            deduped[key] = device
    return list(deduped.values())


def _parse_device(raw: dict[str, Any], station_id: str) -> Device | None:
    device_sn = raw.get("deviceSn") or raw.get("sn")
    if not device_sn:
        return None
    return Device(
        device_sn=str(device_sn),
        device_type=raw.get("deviceType"),
        station_id=station_id,
        device_id=str(raw["deviceId"]) if raw.get("deviceId") is not None else None,
        device_state=raw.get("deviceState"),
        connect_status=raw.get("connectStatus") or raw.get("online"),
        product_id=str(raw["productId"]) if raw.get("productId") is not None else None,
        raw=raw,
    )


def _parse_device_data(raw: dict[str, Any]) -> DeviceData:
    data_list = [
        DataPoint(
            key=str(item["key"]),
            value=str(item.get("value", "")),
            unit=item.get("unit"),
            name=item.get("name"),
        )
        for item in _as_list(raw.get("dataList"))
        if item.get("key") is not None
    ]
    return DeviceData(
        device_sn=str(raw.get("deviceSn", "")),
        device_type=raw.get("deviceType"),
        device_state=raw.get("deviceState"),
        data_list=data_list,
        collection_time=raw.get("collectionTime"),
    )


class DeyeCloudApiClient:
    """Typed async client for DeyeCloud OpenAPI v1."""

    def __init__(
        self,
        *,
        session: aiohttp.ClientSession,
        base_url: str,
        app_id: str,
        app_secret: str,
        username: str,
        password: str,
        company_id: str | None = None,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._app_id = app_id
        self._app_secret = app_secret
        self._username = username
        self._password = password
        self._company_id = company_id
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    @property
    def access_token(self) -> str | None:
        """Return the current access token."""
        return self._access_token

    async def async_authenticate(self, *, force: bool = False) -> None:
        """Authenticate and cache the access token."""
        if (
            not force
            and self._access_token
            and time.monotonic() < self._token_expires_at
        ):
            return

        if force:
            self._access_token = None
            self._token_expires_at = 0.0

        url = f"{self._base_url}/account/token?appId={self._app_id}"
        payload: dict[str, Any] = {
            "appSecret": self._app_secret,
            **_build_login_payload(self._username),
            "password": _sha256(self._password),
        }
        if self._company_id:
            payload["companyId"] = str(self._company_id).strip()

        response = await self._post_json(url, payload=payload)
        if not response.get("success", True):
            raise DeyeCloudAuthError(str(response.get("msg") or "Token request failed"))

        token = response.get("accessToken")
        if not token:
            raise DeyeCloudAuthError("Token response missing accessToken")

        self._access_token = str(token)
        expires_in = response.get("expiresIn")
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            # Refresh one minute before expiry.
            self._token_expires_at = time.monotonic() + float(expires_in) - 60
        else:
            self._token_expires_at = time.monotonic() + 25 * 60

    async def async_get_stations(self) -> list[Station]:
        """Return all stations for the authenticated account."""
        await self.async_authenticate()
        stations: list[Station] = []
        page = 1
        size = 100

        while True:
            response = await self._authorized_post(
                "/station/list",
                {"page": page, "size": size},
            )
            page_items = _as_list(response.get("stationList"))
            for item in page_items:
                if isinstance(item, dict):
                    station = _parse_station(item)
                    if station:
                        stations.append(station)

            total = response.get("total") or response.get("totalCount")
            if total is not None and len(stations) >= int(total):
                break
            if len(page_items) < size:
                break
            page += 1

        return stations

    async def async_get_station_devices(self, station_ids: list[str]) -> list[Device]:
        """Return devices for the given station ids."""
        if not station_ids:
            return []

        await self.async_authenticate()
        numeric_ids: list[int | str] = []
        for station_id in station_ids:
            normalized = normalize_station_id(station_id)
            if normalized is None:
                continue
            try:
                numeric_ids.append(int(float(normalized)))
            except ValueError:
                numeric_ids.append(normalized)

        devices: list[Device] = []
        page = 1
        size = 100

        while True:
            response = await self._authorized_post(
                "/station/device",
                {"page": page, "size": size, "stationIds": numeric_ids},
            )
            page_items = _as_list(response.get("deviceListItems"))
            for item in page_items:
                if not isinstance(item, dict):
                    continue
                raw_station_id = normalize_station_id(
                    item.get("stationId") or item.get("station_id")
                )
                if not raw_station_id and len(station_ids) == 1:
                    raw_station_id = normalize_station_id(station_ids[0])
                if not raw_station_id:
                    continue
                device = _parse_device(item, raw_station_id)
                if device:
                    devices.append(device)

            total = response.get("total") or response.get("totalCount")
            if total is not None and len(devices) >= int(total):
                break
            if len(page_items) < size:
                break
            page += 1

        return _dedupe_devices(devices)

    async def async_get_device_measure_points(
        self, device_sn: str
    ) -> list[MeasurePoint]:
        """Return supported measure points for a device."""
        await self.async_authenticate()
        response = await self._authorized_post(
            "/device/measurePoints",
            {"deviceSn": device_sn},
        )
        return [
            MeasurePoint(
                key=str(item["key"]),
                name=item.get("name"),
                unit=item.get("unit"),
            )
            for item in _as_list(response.get("measurePoints"))
            if isinstance(item, dict) and item.get("key") is not None
        ]

    async def async_get_device_latest(self, device_sns: list[str]) -> list[DeviceData]:
        """Return latest telemetry for devices in API batches."""
        if not device_sns:
            return []

        await self.async_authenticate()
        results: list[DeviceData] = []

        for index in range(0, len(device_sns), DEVICE_LATEST_BATCH_SIZE):
            batch = device_sns[index : index + DEVICE_LATEST_BATCH_SIZE]
            response = await self._authorized_post(
                "/device/latest",
                {"deviceList": batch},
            )
            for item in _as_list(response.get("deviceDataList")):
                if isinstance(item, dict):
                    results.append(_parse_device_data(item))

        return results

    async def async_get_station_latest(self, station_id: str) -> StationData:
        """Return latest station telemetry."""
        await self.async_authenticate()
        normalized = normalize_station_id(station_id)
        if normalized is None:
            raise DeyeCloudApiError(f"Invalid station id: {station_id}")

        response = await self._authorized_post(
            "/station/latest",
            {"stationId": int(float(normalized))},
        )
        return StationData(
            station_id=normalized,
            data=_parse_station_latest_data(response),
        )

    async def _authorized_post(
        self,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        await self.async_authenticate()
        headers = {"Authorization": f"Bearer {self._access_token}"}
        url = f"{self._base_url}{path}"
        try:
            return await self._post_json(url, headers=headers, payload=payload)
        except DeyeCloudAuthError:
            await self.async_authenticate(force=True)
            headers = {"Authorization": f"Bearer {self._access_token}"}
            return await self._post_json(url, headers=headers, payload=payload)

    async def _post_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        timeout: int = 15,
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                async with self._session.post(
                    url,
                    headers=headers,
                    json=payload or {},
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status in {401, 403}:
                        self._access_token = None
                        self._token_expires_at = 0.0
                        raise DeyeCloudAuthError(
                            f"Authentication failed with status {response.status}"
                        )
                    response.raise_for_status()
                    data = await response.json()
                    if not isinstance(data, dict):
                        raise DeyeCloudApiError("API response was not a JSON object")
                    if data.get("success") is False:
                        message = str(data.get("msg") or "API request failed")
                        if "/account/token" in url:
                            raise DeyeCloudAuthError(message)
                        raise DeyeCloudApiError(message)
                    return data
            except DeyeCloudAuthError:
                raise
            except (TimeoutError, aiohttp.ClientError) as exc:
                last_exc = exc
                if attempt == 1:
                    break
                await asyncio.sleep(1)

        raise DeyeCloudConnectionError(str(last_exc or "Connection failed"))
