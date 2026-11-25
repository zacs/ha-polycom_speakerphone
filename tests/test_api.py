"""Tests for the Polycom API client."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.poly.api import PolycomApiClient, PolycomApiClientError
from custom_components.poly.const import DEFAULT_USERNAME

from .conftest import HOST, PASSWORD, RawBody, mock_device

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )


def make_client(hass: HomeAssistant) -> PolycomApiClient:
    """Return a client for the mocked phone."""
    return PolycomApiClient(
        host=HOST,
        username=DEFAULT_USERNAME,
        password=PASSWORD,
        session=async_get_clientsession(hass, verify_ssl=False),
    )


async def test_call_status_when_idle(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Status 4007 from callStatus means no call is active, not a failure."""
    mock_device(aioclient_mock)

    assert await make_client(hass).async_get_call_status() == {}


async def test_call_status_other_status_raises(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Other non-2000 statuses from callStatus are still failures."""
    mock_device(aioclient_mock, call_status=RawBody({"Status": "5000"}))

    with pytest.raises(PolycomApiClientError, match="5000"):
        await make_client(hass).async_get_call_status()


async def test_status_4007_is_a_failure_elsewhere(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Only callStatus treats 4007 as a normal answer; a command can't."""
    mock_device(aioclient_mock, mute=RawBody({"Status": "4007"}))

    with pytest.raises(PolycomApiClientError, match="4007"):
        await make_client(hass).async_set_mute(mute=True)
