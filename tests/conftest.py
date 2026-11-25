"""
Shared fixtures for the Polycom Speakerphone tests.

By default every endpoint answers with an anonymized capture from a real,
idle Trio 8800 (see ``fixtures/README.md``). Tests override single endpoints
to cover other states.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
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

FIXTURES = Path(__file__).parent / "fixtures" / "trio_8800_idle"

HOST = "192.168.1.50"
PASSWORD = "secret"  # noqa: S105
MAC = "64167f123456"

ENDPOINTS: dict[str, tuple[str, str]] = {
    "device_info": ("get", "/api/v2/mgmt/device/info"),
    "poll_status": ("get", "/api/v1/mgmt/pollForStatus"),
    "call_status": ("get", "/api/v1/webCallControl/callStatus"),
    "device_stats": ("get", "/api/v1/mgmt/device/stats"),
    "line_info": ("get", "/api/v2/mgmt/lineInfo"),
    "session_stats": ("get", "/api/v1/mgmt/media/sessionStats"),
    "communication_info": ("get", "/api/v1/mgmt/media/communicationInfo"),
    "mute": ("post", "/api/v1/callctrl/mute"),
    "reboot": ("post", "/api/v1/mgmt/safeReboot"),
}


@dataclass
class RawBody:
    """An override giving the whole response body, not just its ``data``."""

    body: Any


def load_body(name: str) -> Any:
    """Return the captured response body for an endpoint."""
    path = FIXTURES / f"{name}.json"
    if not path.exists():
        # No capture of the command endpoints yet; assume plain success
        return {"Status": "2000"}
    return json.loads(path.read_text())


def load_data(name: str) -> Any:
    """Return the ``data`` part of a captured response, safe to modify."""
    return copy.deepcopy(load_body(name)["data"])


def mock_device(
    aioclient_mock: AiohttpClientMocker,
    host: str = HOST,
    **overrides: Any,
) -> None:
    """
    Register mocked responses for every endpoint of one device.

    An override may be a payload for the response's ``data`` key, a
    ``RawBody`` with the whole response, an ``int`` HTTP status, or an
    exception instance to raise.
    """
    for name, (method, path) in ENDPOINTS.items():
        value = overrides.get(name, RawBody(load_body(name)))
        url = f"https://{host}{path}"
        register = getattr(aioclient_mock, method)
        if isinstance(value, BaseException):
            register(url, exc=value)
        elif isinstance(value, int):
            register(url, status=value)
        elif isinstance(value, RawBody):
            register(url, json=value.body)
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
        unique_id=MAC,
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
