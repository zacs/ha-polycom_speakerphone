"""
Tests for call status, call logs, indicator lights and call control.

No real phone has been captured during a call yet, so these use the shapes in
Poly's REST API reference manual.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.poly.const import DOMAIN

from .conftest import (
    CONNECTED_CALL,
    RawBody,
    get_entity_id,
    mock_device,
    setup_entry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

HOST_URL = "https://192.168.1.50"


def state(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str) -> str:
    """Return an entity's state by its key."""
    return hass.states.get(get_entity_id(hass, platform, entry, key)).state


def posts(aioclient_mock: AiohttpClientMocker) -> list[tuple[str, object]]:
    """Return the path and body of every POST made."""
    return [
        (str(url).removeprefix(HOST_URL), data)
        for method, url, data, _ in aioclient_mock.mock_calls
        if method == "post"
    ]


async def test_connected_call(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A connected call reports who's on it and for how long."""
    mock_device(aioclient_mock, calls=[CONNECTED_CALL])
    await setup_entry(hass, mock_config_entry)

    assert state(hass, mock_config_entry, "sensor", "remote_party") == "Test 1171"
    assert state(hass, mock_config_entry, "sensor", "call_duration") == "25"
    assert state(hass, mock_config_entry, "binary_sensor", "ringing") == STATE_OFF


async def test_ringing_call(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """An incoming call that's ringing turns the ringing sensor on."""
    ringing = {**CONNECTED_CALL, "CallState": "Offering", "Ringing": "1"}
    mock_device(aioclient_mock, calls=[ringing])
    await setup_entry(hass, mock_config_entry)

    assert state(hass, mock_config_entry, "binary_sensor", "ringing") == STATE_ON
    assert state(hass, mock_config_entry, "sensor", "remote_party") == "Test 1171"


async def test_call_falls_back_to_call_status_v1(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Without callStatus version 2, the call comes from version 1."""
    mock_device(
        aioclient_mock,
        calls=404,
        call_status={
            "CallHandle": "9577dd30",
            "Type": "Incoming",
            "Protocol": "SIP",
            "CallState": "Connected",
            "LineID": "1",
            "RemotePartyName": "Kitchen",
            "RemotePartyNumber": "sip:1002@192.0.2.10",
            "DurationInSeconds": "7",
        },
    )
    await setup_entry(hass, mock_config_entry)

    assert state(hass, mock_config_entry, "sensor", "call_duration") == "7"


async def test_last_called_number_prefers_session_stats(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """If session stats carry a last called number, it wins over the call log."""
    mock_device(aioclient_mock, session_stats={"LastCalledNumber": "5551234"})
    await setup_entry(hass, mock_config_entry)

    assert state(hass, mock_config_entry, "sensor", "last_called_number") == "5551234"


@pytest.mark.parametrize(("led", "expected"), [("on", STATE_ON), ("off", STATE_OFF)])
async def test_voicemail_waiting(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    led: str,
    expected: str,
) -> None:
    """The message waiting light shows whether there's voicemail."""
    mock_device(aioclient_mock, led_status={"MWI": {"State": led}})
    await setup_entry(hass, mock_config_entry)

    assert state(hass, mock_config_entry, "binary_sensor", "voicemail") == expected


async def test_unsupported_endpoints_add_no_entities(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Entities for endpoints the phone doesn't answer aren't created."""
    mock_device(
        aioclient_mock,
        calls=404,
        call_logs=RawBody({"Status": "4004"}),
        led_status={"Lines": []},
    )
    await setup_entry(hass, mock_config_entry)

    registry = er.async_get(hass)
    for platform, key in (
        ("binary_sensor", "ringing"),
        ("binary_sensor", "voicemail"),
        ("sensor", "remote_party"),
        ("sensor", "missed_calls"),
    ):
        assert (
            registry.async_get_entity_id(
                platform, DOMAIN, f"{mock_config_entry.entry_id}_{key}"
            )
            is None
        )
    assert state(hass, mock_config_entry, "sensor", "call_duration") == STATE_UNKNOWN


@pytest.mark.parametrize(
    ("service", "data", "expected"),
    [
        (
            "dial",
            {"number": "1002"},
            ("/api/v1/callctrl/dial", {"data": {"Dest": "1002"}}),
        ),
        (
            "dial",
            {"number": "1002", "line": 2},
            ("/api/v1/callctrl/dial", {"data": {"Dest": "1002", "Line": "2"}}),
        ),
        ("answer_call", {}, ("/api/v1/callctrl/answerCall", None)),
        ("reject_call", {}, ("/api/v1/callctrl/rejectCall", None)),
    ],
)
async def test_call_actions(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
    service: str,
    data: dict[str, object],
    expected: tuple[str, object],
) -> None:
    """Each action sends its command to the phone."""
    aioclient_mock.mock_calls.clear()

    await hass.services.async_call(DOMAIN, service, data, blocking=True)

    assert posts(aioclient_mock) == [expected]


@pytest.mark.parametrize(
    "overrides",
    [
        {"calls": [CONNECTED_CALL]},
        # Without callStatus version 2, the handle comes from version 1
        {"calls": 404, "call_status": {"CallHandle": "b5576ff8"}},
    ],
)
async def test_end_call(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
    overrides: dict[str, object],
) -> None:
    """Ending a call hangs up the current call by its handle."""
    aioclient_mock.clear_requests()
    mock_device(aioclient_mock, **overrides)

    await hass.services.async_call(DOMAIN, "end_call", {}, blocking=True)

    assert posts(aioclient_mock) == [
        ("/api/v1/callctrl/endCall", {"data": {"Ref": "b5576ff8"}})
    ]


async def test_end_call_without_a_call(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
) -> None:
    """Ending a call when there isn't one is an error, and sends nothing."""
    aioclient_mock.mock_calls.clear()

    with pytest.raises(ServiceValidationError, match="has no call to end"):
        await hass.services.async_call(DOMAIN, "end_call", {}, blocking=True)
    assert posts(aioclient_mock) == []


async def test_dial_refused(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
) -> None:
    """The phone's reason for refusing a call is passed on."""
    aioclient_mock.clear_requests()
    mock_device(aioclient_mock, dial=RawBody({"Status": "4002"}))

    with pytest.raises(HomeAssistantError, match="Line not registered"):
        await hass.services.async_call(
            DOMAIN, "dial", {"number": "1002"}, blocking=True
        )
