"""Tests for the Polycom Speakerphone entities."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.poly.const import DOMAIN

from .conftest import MAC, load_data, mock_device

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

NOW = "2025-09-01T12:00:00+00:00"


def get_entity_id(
    hass: HomeAssistant, platform: str, entry: MockConfigEntry, key: str
) -> str:
    """Look up an entity by the unique ID the integration has always used."""
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id is not None, f"{platform} {key} not registered"
    return entity_id


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add and set up a config entry."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Advance time to trigger the next coordinator poll."""
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("platform", "key", "expected"),
    [
        ("sensor", "phone_state", "Idle"),
        # Device time is local (test HA time zone is US/Pacific, UTC-7 in August)
        ("sensor", "last_call_time", "2025-08-03T17:35:57+00:00"),
        ("sensor", "call_duration", STATE_UNKNOWN),
        ("sensor", "phone_error", STATE_UNKNOWN),
        ("sensor", "cpu_usage", "35.5"),
        # 284389376 of 519995392 bytes; "Used" includes the page cache
        ("sensor", "memory_usage", "54.7"),
        ("sensor", "memory_total", "495.9"),
        # sessionStats is an empty list while idle
        ("sensor", "last_called_number", STATE_UNKNOWN),
        ("sensor", "sip_connection", "Connected"),
        # NOW minus 15 days, 23 hours, 15 minutes, 32 seconds
        ("sensor", "uptime", "2025-08-16T12:44:28+00:00"),
        ("binary_sensor", "dnd_status", STATE_OFF),
        ("binary_sensor", "mute_status", STATE_OFF),
        ("binary_sensor", "line_registered", STATE_ON),
        ("binary_sensor", "line_active", STATE_OFF),
        ("switch", "mute", STATE_OFF),
        ("button", "reboot", STATE_UNKNOWN),
    ],
)
async def test_entity_states(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    platform: str,
    key: str,
    expected: str,
) -> None:
    """Each entity reports the value parsed from a real idle Trio 8800."""
    freezer.move_to(NOW)
    mock_device(aioclient_mock)
    await setup_entry(hass, mock_config_entry)

    state = hass.states.get(get_entity_id(hass, platform, mock_config_entry, key))
    assert state is not None
    assert state.state == expected


async def test_entity_count(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """All entities are created and tied to the config entry."""
    entries = er.async_entries_for_config_entry(
        er.async_get(hass), init_integration.entry_id
    )
    assert len(entries) == 16  # noqa: PLR2004


@pytest.mark.parametrize(
    ("platform", "key", "name"),
    [
        ("sensor", "phone_state", "Polycom Trio 8800 Phone state"),
        ("sensor", "cpu_usage", "Polycom Trio 8800 CPU usage"),
        ("binary_sensor", "dnd_status", "Polycom Trio 8800 Do not disturb"),
        ("switch", "mute", "Polycom Trio 8800 Mute"),
        ("button", "reboot", "Polycom Trio 8800 Reboot"),
    ],
)
async def test_entity_names(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    platform: str,
    key: str,
    name: str,
) -> None:
    """Entity names come from translations, prefixed by the device name."""
    state = hass.states.get(get_entity_id(hass, platform, init_integration, key))
    assert state.attributes["friendly_name"] == name


async def test_device_info(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The device is registered with its MAC and firmware details."""
    devices = dr.async_entries_for_config_entry(
        dr.async_get(hass), init_integration.entry_id
    )
    assert len(devices) == 1
    device = devices[0]
    assert device.identifiers == {(DOMAIN, MAC)}
    assert device.manufacturer == "Polycom"
    assert device.model == "Trio 8800"
    assert device.name == "Polycom Trio 8800"
    assert device.sw_version == "7.2.8.0031 17-Mar-24 05:02"
    assert device.configuration_url == "https://192.168.1.50"
    assert (dr.CONNECTION_NETWORK_MAC, "64:16:7f:12:34:56") in device.connections


async def test_phone_state_falls_back_to_call_status(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """When pollForStatus is unavailable, callStatus provides the state."""
    # The State field is assumed; no capture of callStatus during a call yet
    mock_device(aioclient_mock, poll_status=500, call_status={"State": "Connected"})
    await setup_entry(hass, mock_config_entry)

    entity_id = get_entity_id(hass, "sensor", mock_config_entry, "phone_state")
    assert hass.states.get(entity_id).state == "Connected"


async def test_optional_endpoints_unavailable(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The integration still loads if only device info is supported."""
    mock_device(
        aioclient_mock,
        poll_status=404,
        call_status=404,
        device_stats=404,
        line_info=404,
        session_stats=404,
        communication_info=404,
    )
    await setup_entry(hass, mock_config_entry)

    def state(platform: str, key: str) -> str:
        return hass.states.get(
            get_entity_id(hass, platform, mock_config_entry, key)
        ).state

    assert state("sensor", "phone_state") == "Idle"
    assert state("sensor", "sip_connection") == "Unknown"
    assert state("sensor", "cpu_usage") == STATE_UNKNOWN
    assert state("sensor", "memory_usage") == STATE_UNKNOWN
    assert state("sensor", "last_call_time") == STATE_UNKNOWN
    assert state("binary_sensor", "dnd_status") == STATE_UNKNOWN
    assert state("binary_sensor", "line_registered") == STATE_UNKNOWN
    assert state("binary_sensor", "mute_status") == STATE_OFF
    assert state("switch", "mute") == STATE_OFF


async def test_state_data_parsing(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Duration and error text are surfaced from pollForStatus StateData."""
    # The StateData wording is assumed; no capture during a call yet
    mock_device(
        aioclient_mock,
        poll_status={"State": "Active", "StateData": "Call duration 00:01:23"},
    )
    await setup_entry(hass, mock_config_entry)

    def state(key: str) -> str:
        return hass.states.get(
            get_entity_id(hass, "sensor", mock_config_entry, key)
        ).state

    assert state("phone_state") == "Active"
    assert state("call_duration") == "Call duration 00:01:23"
    assert state("phone_error") == STATE_UNKNOWN
    assert state("last_call_time") == STATE_UNKNOWN


async def test_device_becomes_unavailable(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Entities go unavailable when the device stops answering, then recover."""
    mock_device(aioclient_mock)
    await setup_entry(hass, mock_config_entry)
    entity_id = get_entity_id(hass, "sensor", mock_config_entry, "phone_state")

    aioclient_mock.clear_requests()
    mock_device(aioclient_mock, device_info=TimeoutError())
    await poll(hass, freezer)
    assert hass.states.get(entity_id).state == "unavailable"

    aioclient_mock.clear_requests()
    mock_device(aioclient_mock)
    await poll(hass, freezer)
    assert hass.states.get(entity_id).state == "Idle"


async def test_uptime_ignores_poll_jitter(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A second of drift between polls doesn't move the boot time; a reboot does."""
    freezer.move_to(NOW)
    mock_device(aioclient_mock)
    await setup_entry(hass, mock_config_entry)
    entity_id = get_entity_id(hass, "sensor", mock_config_entry, "uptime")
    assert hass.states.get(entity_id).state == "2025-08-16T12:44:28+00:00"

    # 30s of wall time passes but the device reports 31s more uptime
    device_info = load_data("device_info")
    device_info["UpTime"] = {
        "Days": "15",
        "Hours": "23",
        "Minutes": "16",
        "Seconds": "3",
    }
    aioclient_mock.clear_requests()
    mock_device(aioclient_mock, device_info=device_info)
    await poll(hass, freezer)
    assert hass.states.get(entity_id).state == "2025-08-16T12:44:28+00:00"

    # Device rebooted a minute before the next poll
    device_info["UpTime"] = {"Days": "0", "Hours": "0", "Minutes": "1", "Seconds": "0"}
    aioclient_mock.clear_requests()
    mock_device(aioclient_mock, device_info=device_info)
    await poll(hass, freezer)
    assert hass.states.get(entity_id).state == "2025-09-01T12:00:00+00:00"


async def test_mute_switch(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
) -> None:
    """The mute switch posts the requested state to the device."""
    entity_id = get_entity_id(hass, "switch", init_integration, "mute")

    for service, expected in (("turn_on", "1"), ("turn_off", "0")):
        aioclient_mock.mock_calls.clear()
        await hass.services.async_call(
            "switch", service, {"entity_id": entity_id}, blocking=True
        )
        mute_calls = [c for c in aioclient_mock.mock_calls if c[0] == "post"]
        assert len(mute_calls) == 1
        assert str(mute_calls[0][1]).endswith("/api/v1/callctrl/mute")
        assert mute_calls[0][2] == {"data": {"state": expected}}


async def test_reboot_button(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
) -> None:
    """Pressing the reboot button triggers a safe reboot."""
    entity_id = get_entity_id(hass, "button", init_integration, "reboot")
    aioclient_mock.mock_calls.clear()

    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )

    assert [str(c[1]) for c in aioclient_mock.mock_calls] == [
        "https://192.168.1.50/api/v1/mgmt/safeReboot"
    ]
