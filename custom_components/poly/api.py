"""Polycom Trio 8800 API Client."""

from __future__ import annotations

import asyncio
import base64
import socket
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

REQUEST_TIMEOUT = 10
API_STATUS_OK = "2000"


class PolycomApiClientError(Exception):
    """Exception to indicate a general API error."""


class PolycomApiClientCommunicationError(
    PolycomApiClientError,
):
    """Exception to indicate a communication error."""


class PolycomApiClientAuthenticationError(
    PolycomApiClientError,
):
    """Exception to indicate an authentication error."""


def _verify_response_or_raise(response: aiohttp.ClientResponse) -> None:
    """Verify that the response is valid."""
    if response.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
        msg = "Invalid credentials"
        raise PolycomApiClientAuthenticationError(msg)
    response.raise_for_status()


def _verify_status_or_raise(body: Any) -> None:
    """
    Raise if the device reports a failure inside an HTTP 200 reply.

    Poly phones answer most requests with HTTP 200 and put the outcome in a
    "Status" field: "2000" is success, 4xxx/5xxx are errors (for example
    callStatus returns "4007" when no call is active).
    """
    if isinstance(body, dict) and (status := body.get("Status")) not in (
        None,
        API_STATUS_OK,
    ):
        msg = f"Device returned status {status}"
        raise PolycomApiClientError(msg)


def device_mac_address(device_info: dict[str, Any]) -> str | None:
    """
    Return the phone's MAC address as used for unique IDs and devices.

    Only device info carries it (as 12 lowercase hex digits on a Trio 8800);
    network info doesn't include it.
    """
    mac_address = device_info.get("MACAddress")
    return str(mac_address).lower() if mac_address else None


class PolycomApiClient:
    """Polycom Trio 8800 API Client."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        *,
        verify_ssl: bool = False,
    ) -> None:
        """Initialize Polycom API Client."""
        self._host = host
        self._session = session
        self._verify_ssl = verify_ssl
        self._base_url = f"https://{host}/api/v1"
        # Built by hand: aiohttp.BasicAuth is deprecated in newer aiohttp, and
        # its replacement doesn't exist in the versions older HA releases ship
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }

    async def async_get_device_info(self) -> dict[str, Any]:
        """Get device information."""
        response = await self._api_wrapper(
            method="get",
            url=f"https://{self._host}/api/v2/mgmt/device/info",
        )
        return response.get("data", {})

    async def async_get_call_status(self) -> dict[str, Any]:
        """Get current call status."""
        response = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/webCallControl/callStatus",
        )
        # This endpoint may return an error status when no call is active
        return response.get("data", {})

    async def async_get_session_stats(self) -> Any:
        """Get media session statistics (an empty list while idle)."""
        response = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/mgmt/media/sessionStats",
        )
        return response.get("data", {})

    async def async_get_line_info(self) -> list[dict[str, Any]]:
        """Get line registration information."""
        response = await self._api_wrapper(
            method="get",
            url=f"https://{self._host}/api/v2/mgmt/lineInfo",
        )
        return response.get("data", [])

    async def async_get_device_stats(self) -> dict[str, Any]:
        """Get device statistics like CPU and memory."""
        response = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/mgmt/device/stats",
        )
        return response.get("data", {})

    async def async_poll_for_status(self) -> dict[str, Any]:
        """Poll for device status - optimized endpoint for fast polling."""
        response = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/mgmt/pollForStatus",
        )
        return response.get("data", {})

    async def async_get_communication_info(self) -> dict[str, Any]:
        """Get communication information including mute state."""
        response = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/mgmt/media/communicationInfo",
        )
        return response.get("data", {})

    async def async_set_mute(self, *, mute: bool) -> dict[str, Any]:
        """Set the mute state of the phone."""
        return await self._api_wrapper(
            method="post",
            url=f"{self._base_url}/callctrl/mute",
            data={"data": {"state": "1" if mute else "0"}},
        )

    async def async_reboot(self) -> dict[str, Any]:
        """Reboot the device once any active call has ended."""
        return await self._api_wrapper(
            method="post",
            url=f"{self._base_url}/mgmt/safeReboot",
        )

    async def async_get_all_data(self) -> dict[str, Any]:
        """
        Get all polled device data.

        Device info is required; every other endpoint is optional because
        firmware versions differ in which ones they support.
        """
        device_info = await self.async_get_device_info()

        # Fetched one at a time to avoid overwhelming the phone's web server
        optional: dict[str, Callable[[], Awaitable[Any]]] = {
            "poll_status": self.async_poll_for_status,
            "call_status": self.async_get_call_status,
            "device_stats": self.async_get_device_stats,
            "line_info": self.async_get_line_info,
            "session_stats": self.async_get_session_stats,
            "communication_info": self.async_get_communication_info,
        }
        data: dict[str, Any] = {"device_info": device_info}
        for key, fetch in optional.items():
            try:
                data[key] = await fetch()
            except PolycomApiClientError:
                data[key] = [] if key == "line_info" else {}
        return data

    async def _api_wrapper(
        self,
        method: str,
        url: str,
        data: dict | None = None,
    ) -> Any:
        """Make a request to the device and return the decoded JSON body."""
        try:
            async with (
                asyncio.timeout(REQUEST_TIMEOUT),
                self._session.request(
                    method=method,
                    url=url,
                    headers=self._headers,
                    json=data,
                    ssl=self._verify_ssl,
                ) as response,
            ):
                _verify_response_or_raise(response)
                body = await response.json()
                _verify_status_or_raise(body)
                return body

        except PolycomApiClientError:
            # Let our own errors (e.g. bad credentials) through unwrapped
            raise
        except TimeoutError as exception:
            msg = f"Timeout error fetching information - {exception}"
            raise PolycomApiClientCommunicationError(msg) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error fetching information - {exception}"
            raise PolycomApiClientCommunicationError(msg) from exception
        except ValueError as exception:
            msg = f"Unexpected response from device - {exception}"
            raise PolycomApiClientError(msg) from exception
