"""
Tests for call status, call logs and call control.

Calls in progress use an anonymized capture from a real Trio 8800 during an
outgoing call. No ringing call or command response has been captured yet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.poly.const import DOMAIN

from .conftest import (
    IN_CALL,
    RINGING,
    RawBody,
    get_entity_id,
    mock_device,
    setup_entry,
)

if TYPE_CHECKING:
    from collections.abc import Callable

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


@pytest.mark.parametrize(
    ("platform", "key", "expected"),
    [
        ("sensor", "phone_state", "Active"),
        ("sensor", "call_duration", "132"),
        ("sensor", "remote_party", "Office Speakerphone"),
        ("sensor", "last_called_number", "1003"),
        ("sensor", "missed_calls", "2"),
        ("sensor", "last_call_time", STATE_UNKNOWN),
        ("binary_sensor", "ringing", STATE_OFF),
        ("binary_sensor", "line_active", STATE_ON),
        ("binary_sensor", "mute_status", STATE_OFF),
        ("switch", "mute", STATE_OFF),
    ],
)
async def test_call_in_progress(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    platform: str,
    key: str,
    expected: str,
) -> None:
    """Entities during a real outgoing call on a Trio 8800."""
    mock_device(aioclient_mock, capture=IN_CALL)
    await setup_entry(hass, mock_config_entry)

    assert state(hass, mock_config_entry, platform, key) == expected


@pytest.mark.parametrize(
    ("platform", "key", "expected"),
    [
        ("binary_sensor", "ringing", STATE_ON),
        ("sensor", "remote_party", "Kitchen Phone"),
        ("sensor", "call_duration", "0"),
        # pollForStatus keeps reporting Idle while a call rings
        ("sensor", "phone_state", "Idle"),
        ("binary_sensor", "line_active", STATE_ON),
    ],
)
async def test_ringing_call(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    platform: str,
    key: str,
    expected: str,
) -> None:
    """Entities while an incoming call rings on a real Trio 8800."""
    mock_device(aioclient_mock, capture=RINGING)
    await setup_entry(hass, mock_config_entry)

    assert state(hass, mock_config_entry, platform, key) == expected


async def test_ringing_call_status_v1_duration(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """CallStatus version 1's duration of -1 while ringing isn't shown."""
    mock_device(aioclient_mock, capture=RINGING, calls=404)
    await setup_entry(hass, mock_config_entry)

    assert state(hass, mock_config_entry, "sensor", "call_duration") == STATE_UNKNOWN
    assert state(hass, mock_config_entry, "sensor", "remote_party") == "Kitchen Phone"


async def test_call_falls_back_to_call_status_v1(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Without callStatus version 2, the call comes from version 1."""
    mock_device(aioclient_mock, capture=IN_CALL, calls=404)
    await setup_entry(hass, mock_config_entry)

    assert state(hass, mock_config_entry, "sensor", "call_duration") == "131"
    assert (
        state(hass, mock_config_entry, "sensor", "remote_party")
        == "Office Speakerphone"
    )


@pytest.mark.parametrize("casing", [str.lower, str.title])
async def test_call_logs(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    casing: Callable[[str], str],
) -> None:
    """Call logs are read whether the lists are "missed" (manual) or "Missed"."""
    placed = [
        {"StartTime": "2025-08-01T09:00:00", "RemotePartyNumber": "1004"},
        {"StartTime": "2025-08-03T10:35:57", "RemotePartyNumber": "1002"},
        {"StartTime": "2025-08-02T12:00:00", "RemotePartyNumber": "1003"},
    ]
    mock_device(
        aioclient_mock,
        call_logs={casing("missed"): [{}, {}, {}], casing("placed"): placed},
    )
    await setup_entry(hass, mock_config_entry)

    assert state(hass, mock_config_entry, "sensor", "missed_calls") == "3"
    # The newest by start time, wherever it is in the list
    assert state(hass, mock_config_entry, "sensor", "last_called_number") == "1002"


async def test_unsupported_endpoints_add_no_entities(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Entities for endpoints the phone doesn't answer aren't created."""
    mock_device(
        aioclient_mock,
        calls=404,
        call_status=404,
        call_logs=RawBody({"Status": "4004"}),
    )
    await setup_entry(hass, mock_config_entry)

    registry = er.async_get(hass)
    for platform, key in (
        ("binary_sensor", "ringing"),
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
        # SIP addresses are dialed as SIP, without the scheme (manual's example)
        (
            "dial",
            {"number": "sip:1002@example.com"},
            (
                "/api/v1/callctrl/dial",
                {"data": {"Dest": "1002@example.com", "Type": "SIP"}},
            ),
        ),
        (
            "dial",
            {"number": "1002@example.com"},
            (
                "/api/v1/callctrl/dial",
                {"data": {"Dest": "1002@example.com", "Type": "SIP"}},
            ),
        ),
        ("answer_call", {}, ("/api/v1/callctrl/answerCall", None)),
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
        {},
        # Without callStatus version 2, the handle comes from version 1, which
        # writes it as "0x4a0ae008"
        {"calls": 404},
    ],
)
async def test_end_call(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
    overrides: dict[str, object],
) -> None:
    """Ending a call hangs up the current call by its version 2 handle."""
    aioclient_mock.clear_requests()
    mock_device(aioclient_mock, capture=IN_CALL, **overrides)

    await hass.services.async_call(DOMAIN, "end_call", {}, blocking=True)

    assert posts(aioclient_mock) == [
        ("/api/v1/callctrl/endCall", {"data": {"Ref": "4a0ae008"}})
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


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        # Without callStatus version 2, version 1 says "Offering" instead
        {"calls": 404},
    ],
)
async def test_reject_call(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
    overrides: dict[str, object],
) -> None:
    """Rejecting sends the ringing call's handle; without it the phone refuses."""
    aioclient_mock.clear_requests()
    mock_device(aioclient_mock, capture=RINGING, **overrides)

    await hass.services.async_call(DOMAIN, "reject_call", {}, blocking=True)

    assert posts(aioclient_mock) == [
        ("/api/v1/callctrl/rejectCall", {"data": {"Ref": "41d9d008"}})
    ]


@pytest.mark.parametrize("capture", [IN_CALL, "trio_8800_idle"])
async def test_reject_call_without_a_ringing_call(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
    capture: str,
) -> None:
    """Rejecting when nothing is ringing is an error, and sends nothing."""
    aioclient_mock.clear_requests()
    mock_device(aioclient_mock, capture=capture)

    with pytest.raises(ServiceValidationError, match="has no incoming call to reject"):
        await hass.services.async_call(DOMAIN, "reject_call", {}, blocking=True)
    assert posts(aioclient_mock) == []
