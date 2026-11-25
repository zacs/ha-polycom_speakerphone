"""Tests for the Polycom API client."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)

from custom_components.poly.api import PolycomApiClient, PolycomApiClientError
from custom_components.poly.const import DEFAULT_USERNAME

from .conftest import HOST, PASSWORD, RawBody, mock_device

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )
    from yarl import URL


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

    with pytest.raises(PolycomApiClientError, match=r"4007 \(Call does not exist\)"):
        await make_client(hass).async_set_mute(mute=True)


async def test_mute_without_change_is_not_an_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """4003 answers a mute request that wouldn't change the mute state."""
    mock_device(aioclient_mock, mute=RawBody({"Status": "4003"}))

    await make_client(hass).async_set_mute(mute=True)


async def test_requests_are_sent_one_at_a_time(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The phone can't handle parallel requests, so the client never sends them."""
    in_flight = 0
    most_in_flight = 0

    async def slow_response(
        method: str, url: URL, data: Any
    ) -> AiohttpClientMockResponse:
        nonlocal in_flight, most_in_flight
        in_flight += 1
        most_in_flight = max(most_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return AiohttpClientMockResponse(
            method, url, json={"Status": "2000", "data": {}}
        )

    for path in ("/api/v1/mgmt/pollForStatus", "/api/v1/mgmt/device/stats"):
        aioclient_mock.get(f"https://{HOST}{path}", side_effect=slow_response)
    client = make_client(hass)

    await asyncio.gather(
        client.async_poll_for_status(),
        client.async_get_device_stats(),
        client.async_poll_for_status(),
    )

    assert most_in_flight == 1
