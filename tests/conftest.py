"""
Shared fixtures for the Polycom Speakerphone tests.

The payloads below mirror the fields the integration parses from the Poly
REST API. They are synthesized from the integration's own parsing logic, not
captured from a real device.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_VERIFY_SSL
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.poly.const import DOMAIN

if TYPE_CHECKING:
    from collections.abc import Generator

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

HOST = "192.168.1.50"
PASSWORD = "secret"  # noqa: S105
MAC = "64167F123456"

ENDPOINTS: dict[str, tuple[str, str]] = {
    "device_info": ("get", "/api/v2/mgmt/device/info"),
    "network_info": ("get", "/api/v1/mgmt/network/info"),
    "poll_status": ("get", "/api/v1/mgmt/pollForStatus"),
    "call_status": ("get", "/api/v1/webCallControl/callStatus"),
    "device_stats": ("get", "/api/v1/mgmt/device/stats"),
    "line_info": ("get", "/api/v2/mgmt/lineInfo"),
    "session_stats": ("get", "/api/v1/mgmt/media/sessionStats"),
    "communication_info": ("get", "/api/v1/mgmt/media/communicationInfo"),
    "mute": ("post", "/api/v1/callctrl/mute"),
    "reboot": ("post", "/api/v1/mgmt/safeReboot"),
}

DEFAULT_PAYLOADS: dict[str, Any] = {
    "device_info": {
        "ModelNumber": "Trio 8800",
        "DeviceVendor": "Polycom",
        "MACAddress": MAC,
        "Firmware": {"Application": "7.2.6.0019"},
        "UpTime": {"Days": "1", "Hours": "2", "Minutes": "3", "Seconds": "4"},
    },
    "network_info": {"MACAddress": MAC, "IPV4Address": HOST},
    "poll_status": {
        "State": "Idle",
        "StateData": "Time of last call 2025-08-03T10:35:57",
    },
    "call_status": {"State": "Connected"},
    "device_stats": {
        "CPU": {"Current": "12.5", "Average": "10.0"},
        "Memory": {"Total": "1073741824", "Used": "536870912"},
    },
    "line_info": [
        {
            "LineNumber": "1",
            "RegistrationStatus": "Registered",
            "DoNotDisturb": "False",
            "Active": "True",
            "CallServers": [{"Working": "True"}],
        }
    ],
    "session_stats": {"LastCalledNumber": "5551234"},
    "communication_info": {"PhoneMuteState": "False"},
    "mute": {},
    "reboot": {},
}


def mock_device(
    aioclient_mock: AiohttpClientMocker,
    host: str = HOST,
    **overrides: Any,
) -> None:
    """
    Register mocked responses for every endpoint of one device.

    An override may be a payload for the response's ``data`` key, an ``int``
    HTTP status, or an exception instance to raise.
    """
    for name, (method, path) in ENDPOINTS.items():
        value = overrides.get(name, copy.deepcopy(DEFAULT_PAYLOADS[name]))
        url = f"https://{host}{path}"
        register = getattr(aioclient_mock, method)
        if isinstance(value, BaseException):
            register(url, exc=value)
        elif isinstance(value, int):
            register(url, status=value)
        else:
            register(url, json={"Status": "2000", "data": value})


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Enable loading the custom integration in every test."""
    return


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry as created by the config flow."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Polycom Trio 8800",
        unique_id=MAC.lower(),
        data={CONF_HOST: HOST, CONF_PASSWORD: PASSWORD, CONF_VERIFY_SSL: False},
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> MockConfigEntry:
    """Set up the integration against a fully working mocked device."""
    mock_device(aioclient_mock)
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
