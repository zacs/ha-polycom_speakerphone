"""Polycom Trio 8800 API Client."""

from __future__ import annotations

import socket
from typing import Any

import aiohttp
import async_timeout


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
    if response.status in (401, 403):
        msg = "Invalid credentials"
        raise PolycomApiClientAuthenticationError(
            msg,
        )
    response.raise_for_status()


class PolycomApiClient:
    """Polycom Trio 8800 API Client."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        verify_ssl: bool = False,
    ) -> None:
        """Initialize Polycom API Client."""
        self._host = host
        self._username = username
        self._password = password
        self._session = session
        self._verify_ssl = verify_ssl
        self._base_url = f"https://{host}/api/v1"
        self._auth = aiohttp.BasicAuth(username, password)

    async def async_get_device_info(self) -> dict[str, Any]:
        """Get device information."""
        return await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/mgmt/device/info",
        )

    async def async_get_network_info(self) -> dict[str, Any]:
        """Get network information including MAC address."""
        return await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/mgmt/network/info",
        )

    async def async_get_call_status(self) -> dict[str, Any]:
        """Get current call status."""
        return await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/webCallControl/callStatus",
        )

    async def async_get_session_stats(self) -> dict[str, Any]:
        """Get session statistics."""
        return await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/mgmt/media/sessionStats",
        )

    async def async_get_line_info(self) -> dict[str, Any]:
        """Get line registration information."""
        return await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/mgmt/lineInfo",
        )

    async def async_get_device_stats(self) -> dict[str, Any]:
        """Get device statistics like CPU and memory."""
        return await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/mgmt/device/stats",
        )

    async def async_get_dnd_status(self) -> dict[str, Any]:
        """Get Do Not Disturb status."""
        return await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/mgmt/doNotDisturb",
        )

    async def async_set_dnd(self, enabled: bool) -> dict[str, Any]:
        """Set Do Not Disturb status."""
        return await self._api_wrapper(
            method="post",
            url=f"{self._base_url}/mgmt/doNotDisturb",
            data={"enabled": enabled},
        )

    async def async_get_volume(self) -> dict[str, Any]:
        """Get volume level."""
        return await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/mgmt/audio/volume",
        )

    async def async_set_volume(self, volume: int) -> dict[str, Any]:
        """Set volume level (0-100)."""
        return await self._api_wrapper(
            method="post",
            url=f"{self._base_url}/mgmt/audio/volume",
            data={"volume": volume},
        )

    async def async_reboot(self) -> dict[str, Any]:
        """Reboot the device."""
        return await self._api_wrapper(
            method="post",
            url=f"{self._base_url}/mgmt/reboot",
        )

    async def async_get_all_data(self) -> dict[str, Any]:
        """Get all device data at once."""
        device_info = await self.async_get_device_info()
        network_info = await self.async_get_network_info()
        
        # Try to get other data, but don't fail if endpoints don't exist
        try:
            call_status = await self.async_get_call_status()
        except Exception:  # noqa: BLE001
            call_status = {}
        
        try:
            dnd_status = await self.async_get_dnd_status()
        except Exception:  # noqa: BLE001
            dnd_status = {}
        
        try:
            volume = await self.async_get_volume()
        except Exception:  # noqa: BLE001
            volume = {}
        
        try:
            device_stats = await self.async_get_device_stats()
        except Exception:  # noqa: BLE001
            device_stats = {}
        
        try:
            line_info = await self.async_get_line_info()
        except Exception:  # noqa: BLE001
            line_info = {}
        
        try:
            session_stats = await self.async_get_session_stats()
        except Exception:  # noqa: BLE001
            session_stats = {}

        return {
            "device_info": device_info,
            "network_info": network_info,
            "call_status": call_status,
            "dnd_status": dnd_status,
            "volume": volume,
            "device_stats": device_stats,
            "line_info": line_info,
            "session_stats": session_stats,
        }

    async def _api_wrapper(
        self,
        method: str,
        url: str,
        data: dict | None = None,
        headers: dict | None = None,
    ) -> Any:
        """Get information from the API."""
        if headers is None:
            headers = {}
        headers["Content-Type"] = "application/json"
        
        try:
            async with async_timeout.timeout(10):
                response = await self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                    auth=self._auth,
                    ssl=self._verify_ssl,
                )
                _verify_response_or_raise(response)
                return await response.json()

        except TimeoutError as exception:
            msg = f"Timeout error fetching information - {exception}"
            raise PolycomApiClientCommunicationError(
                msg,
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error fetching information - {exception}"
            raise PolycomApiClientCommunicationError(
                msg,
            ) from exception
        except Exception as exception:  # pylint: disable=broad-except
            msg = f"Something really wrong happened! - {exception}"
            raise PolycomApiClientError(
                msg,
            ) from exception
