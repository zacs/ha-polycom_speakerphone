"""Polycom Trio 8800 API Client."""

from __future__ import annotations

import asyncio
import base64
import logging
import socket
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

LOGGER = logging.getLogger(__package__)

REQUEST_TIMEOUT = 10

# The "Status" codes from the Error Codes table of Poly's "UC Software and Poly
# Voice Software REST API Reference Manual"
API_STATUS_OK = "2000"
API_STATUS_NOT_ALLOWED = "4003"
API_STATUS_NO_CALL = "4007"
API_STATUS_DEFAULT_PASSWORD = "4010"  # noqa: S105 (a status code)
API_STATUS_DESCRIPTIONS = {
    "4000": "Invalid input parameters",
    "4001": "Device busy",
    "4002": "Line not registered",
    API_STATUS_NOT_ALLOWED: "Operation not allowed",
    "4004": "Operation not supported",
    "4005": "Line does not exist",
    "4006": "URLs not configured",
    API_STATUS_NO_CALL: "Call does not exist",
    "4008": "Configuration export failed",
    "4009": "Input size limit exceeded",
    API_STATUS_DEFAULT_PASSWORD: "Default password not allowed",
    "4011": "Contact not found",
    "4400": "Bad request",
    "4403": "Forbidden",
    "5000": "Failed to process request",
    "5500": "Internal server error",
}


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


class PolycomApiClientStatusError(PolycomApiClientError):
    """The phone refused a request and gave the reason in its "Status" field."""

    def __init__(self, status: str) -> None:
        """Initialize with the phone's status code."""
        self.status = status
        description = API_STATUS_DESCRIPTIONS.get(status, "Unknown status")
        super().__init__(f"Device returned status {status} ({description})")


def _verify_response_or_raise(response: aiohttp.ClientResponse) -> None:
    """Verify that the response is valid."""
    if response.status == HTTPStatus.UNAUTHORIZED:
        msg = "Invalid credentials"
        raise PolycomApiClientAuthenticationError(msg)
    if response.status == HTTPStatus.FORBIDDEN:
        # The phone handles one request at a time and may answer 403 to one
        # that arrives while another is in progress, so this isn't a bad password
        msg = "Device busy with another request"
        raise PolycomApiClientCommunicationError(msg)
    response.raise_for_status()


def _verify_status_or_raise(body: Any, expected: frozenset[str]) -> None:
    """
    Raise if the device refused a request inside an HTTP 200 reply.

    Poly phones answer with HTTP 200 and put the outcome in a "Status" field:
    "2000" is success and 4xxx/5xxx mean the request wasn't carried out (for
    example a mute command the phone rejects). Some of those codes are normal
    answers for a particular endpoint, so callers say which they expect.
    """
    if isinstance(body, dict) and (status := body.get("Status")) not in (
        None,
        *expected,
    ):
        raise PolycomApiClientStatusError(str(status))


def device_mac_address(device_info: dict[str, Any]) -> str | None:
    """
    Return the phone's MAC address as used for unique IDs and devices.

    Only device info carries it (as 12 lowercase hex digits on a Trio 8800);
    network info doesn't include it.
    """
    mac_address = device_info.get("MACAddress")
    return str(mac_address).lower() if mac_address else None


def active_call(calls: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the connected call if there is one, otherwise the first call."""
    return next(
        (call for call in calls if call.get("CallState") == "Connected"),
        calls[0] if calls else None,
    )


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
        # The phone can't process requests in parallel, so send one at a time
        self._lock = asyncio.Lock()
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
        """Get current call status; empty while no call is active."""
        response = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/webCallControl/callStatus",
            expected_statuses=frozenset({API_STATUS_OK, API_STATUS_NO_CALL}),
        )
        # Idle replies are {"Status": "4007", "Error": ""}, with no data
        return response.get("data", {})

    async def async_get_calls(self) -> list[dict[str, Any]]:
        """Get every call on the phone (callStatus version 2); empty when idle."""
        response = await self._api_wrapper(
            method="get",
            url=f"https://{self._host}/api/v2/webCallControl/callStatus",
            expected_statuses=frozenset({API_STATUS_OK, API_STATUS_NO_CALL}),
        )
        calls = response.get("data", [])
        return (
            [call for call in calls if isinstance(call, dict)]
            if isinstance(calls, list)
            else []
        )

    async def async_get_call_logs(self) -> dict[str, Any]:
        """Get the missed, received and placed call logs."""
        response = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/mgmt/callLogs",
        )
        return response.get("data", {})

    async def async_get_led_status(self) -> dict[str, Any]:
        """Get the state of the phone's indicator lights, e.g. message waiting."""
        response = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/mgmt/ledStatus",
        )
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
        """
        Set the mute state of the phone.

        The phone answers 4003 when the request wouldn't change the mute state
        (already muted, say), which isn't a failure. It answers 4007 when
        there's no call to mute.
        """
        return await self._api_wrapper(
            method="post",
            url=f"{self._base_url}/callctrl/mute",
            data={"data": {"state": "1" if mute else "0"}},
            expected_statuses=frozenset({API_STATUS_OK, API_STATUS_NOT_ALLOWED}),
        )

    async def async_reboot(self) -> dict[str, Any]:
        """Reboot the device once any active call has ended."""
        return await self._api_wrapper(
            method="post",
            url=f"{self._base_url}/mgmt/safeReboot",
        )

    async def async_dial(self, number: str, line: int | None = None) -> None:
        """Call a number or SIP URI, on line 1 unless another is given."""
        call: dict[str, str] = {"Dest": number}
        if line is not None:
            call["Line"] = str(line)
        await self._api_wrapper(
            method="post",
            url=f"{self._base_url}/callctrl/dial",
            data={"data": call},
        )

    async def async_answer_call(self) -> None:
        """Answer the incoming call."""
        await self._api_wrapper(
            method="post", url=f"{self._base_url}/callctrl/answerCall"
        )

    async def async_reject_call(self) -> None:
        """Reject the incoming call."""
        await self._api_wrapper(
            method="post", url=f"{self._base_url}/callctrl/rejectCall"
        )

    async def async_end_call(self, call_handle: str) -> None:
        """End a call, identified by its handle from callStatus."""
        await self._api_wrapper(
            method="post",
            url=f"{self._base_url}/callctrl/endCall",
            data={"data": {"Ref": call_handle}},
        )

    async def async_get_all_data(self) -> dict[str, Any]:
        """
        Get all polled device data.

        Device info is required; every other endpoint is optional because
        firmware versions differ in which ones they support. An optional
        endpoint that fails is left out of the result.
        """
        device_info = await self.async_get_device_info()

        # Fetched one at a time; the phone can't handle parallel requests
        optional: dict[str, Callable[[], Awaitable[Any]]] = {
            "poll_status": self.async_poll_for_status,
            "call_status": self.async_get_call_status,
            "calls": self.async_get_calls,
            "call_logs": self.async_get_call_logs,
            "device_stats": self.async_get_device_stats,
            "line_info": self.async_get_line_info,
            "led_status": self.async_get_led_status,
            "session_stats": self.async_get_session_stats,
            "communication_info": self.async_get_communication_info,
        }
        data: dict[str, Any] = {"device_info": device_info}
        for key, fetch in optional.items():
            try:
                data[key] = await fetch()
            except PolycomApiClientError as exception:
                LOGGER.debug("Skipping %s: %s", key, exception)
        return data

    async def _api_wrapper(
        self,
        method: str,
        url: str,
        data: dict | None = None,
        expected_statuses: frozenset[str] = frozenset({API_STATUS_OK}),
    ) -> Any:
        """Make a request to the device and return the decoded JSON body."""
        try:
            async with (
                self._lock,
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
                _verify_status_or_raise(body, expected_statuses)
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
