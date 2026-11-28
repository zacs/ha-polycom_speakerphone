"""Tests for setting up and unloading the Polycom Speakerphone integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from aiohttp import ClientError
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_VERIFY_SSL
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.poly.const import DOMAIN

from .conftest import MAC, PASSWORD, RawBody, load_data, mock_device

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

REBOOT_PATH = "/api/v1/mgmt/safeReboot"


def reboot_calls(aioclient_mock: AiohttpClientMocker) -> list[str]:
    """Return the URLs of every reboot request made."""
    return [str(c[1]) for c in aioclient_mock.mock_calls if REBOOT_PATH in str(c[1])]


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The entry loads, and unloads cleanly."""
    assert init_integration.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def test_requests_use_basic_auth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
) -> None:
    """Every request authenticates as the phone's built-in Polycom user."""
    assert aioclient_mock.mock_calls
    for _, _, _, headers in aioclient_mock.mock_calls:
        # base64 of "Polycom:secret"
        assert headers["Authorization"] == "Basic UG9seWNvbTpzZWNyZXQ="


@pytest.mark.parametrize(
    "error", [ClientError(), TimeoutError(), 403, 500, RawBody({"Status": "5000"})]
)
async def test_setup_retries_when_device_offline(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    error: Exception | int | RawBody,
) -> None:
    """An unreachable device puts the entry in retry rather than failing it."""
    mock_device(aioclient_mock, device_info=error)
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_starts_reauth_on_bad_password(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A rejected password fails setup and asks the user to reauthenticate."""
    mock_device(aioclient_mock, device_info=401)
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH
    assert flows[0]["context"]["entry_id"] == mock_config_entry.entry_id


async def test_reboot_service_single_device(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
) -> None:
    """With one device, the reboot action needs no arguments."""
    aioclient_mock.mock_calls.clear()

    await hass.services.async_call(DOMAIN, "reboot", {}, blocking=True)

    assert reboot_calls(aioclient_mock) == [f"https://192.168.1.50{REBOOT_PATH}"]


async def _setup_two_devices(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> tuple[MockConfigEntry, MockConfigEntry]:
    """Set up two phones at different addresses."""
    entries = []
    for host, mac in (("10.0.0.1", "64167f000001"), ("10.0.0.2", "64167f000002")):
        mock_device(
            aioclient_mock,
            host=host,
            device_info={**load_data("device_info"), "MACAddress": mac},
        )
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id=mac,
            data={CONF_HOST: host, CONF_PASSWORD: PASSWORD, CONF_VERIFY_SSL: False},
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entries.append(entry)
    return entries[0], entries[1]


async def test_reboot_service_targets_requested_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """With several phones, the action reboots only the one asked for."""
    first, second = await _setup_two_devices(hass, aioclient_mock)
    aioclient_mock.mock_calls.clear()

    await hass.services.async_call(
        DOMAIN, "reboot", {"config_entry_id": first.entry_id}, blocking=True
    )
    assert reboot_calls(aioclient_mock) == [f"https://10.0.0.1{REBOOT_PATH}"]

    # Unloading one phone must not remove the action for the other
    assert await hass.config_entries.async_unload(first.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.mock_calls.clear()

    await hass.services.async_call(
        DOMAIN, "reboot", {"config_entry_id": second.entry_id}, blocking=True
    )
    assert reboot_calls(aioclient_mock) == [f"https://10.0.0.2{REBOOT_PATH}"]


async def test_reboot_service_requires_target_with_several_devices(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """With several phones, omitting the target is an error, not a guess."""
    await _setup_two_devices(hass, aioclient_mock)
    aioclient_mock.mock_calls.clear()

    with pytest.raises(ServiceValidationError, match="choose which to use"):
        await hass.services.async_call(DOMAIN, "reboot", {}, blocking=True)
    assert reboot_calls(aioclient_mock) == []


async def test_reboot_service_rejects_unknown_entry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """An entry ID that isn't a loaded Polycom phone is rejected."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "reboot", {"config_entry_id": "not-a-real-entry"}, blocking=True
        )


async def test_reboot_service_reports_device_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
) -> None:
    """A failed reboot request surfaces as an error to the caller."""
    aioclient_mock.clear_requests()
    mock_device(aioclient_mock, reboot=ClientError())

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, "reboot", {}, blocking=True)


async def test_backfills_unique_id_for_older_entries(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Entries from the old config flow have no unique ID; setup adds the MAC."""
    mock_device(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PASSWORD: PASSWORD},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.unique_id == MAC


async def test_backfill_leaves_duplicate_entries_alone(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A second entry for an already-identified phone isn't given its MAC too."""
    mock_device(aioclient_mock)
    mock_config_entry.add_to_hass(hass)
    duplicate = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PASSWORD: PASSWORD},
    )
    duplicate.add_to_hass(hass)

    await hass.config_entries.async_setup(duplicate.entry_id)
    await hass.async_block_till_done()

    assert duplicate.state is ConfigEntryState.LOADED
    assert duplicate.unique_id is None


@pytest.mark.parametrize(
    ("domain", "service", "key", "endpoint"),
    [
        ("switch", "turn_on", "mute", "mute"),
        ("button", "press", "reboot", "reboot"),
    ],
)
async def test_entity_actions_report_device_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
    domain: str,
    service: str,
    key: str,
    endpoint: str,
) -> None:
    """A failed switch or button request surfaces as a Home Assistant error."""
    entity_id = er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, f"{init_integration.entry_id}_{key}"
    )
    for failure in (ClientError(), RawBody({"Status": "4007"})):
        aioclient_mock.clear_requests()
        mock_device(aioclient_mock, **{endpoint: failure})

        with pytest.raises(HomeAssistantError, match="did not accept the command"):
            await hass.services.async_call(
                domain, service, {"entity_id": entity_id}, blocking=True
            )


def _device_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Return the ID of a phone's device."""
    return dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0].id


async def test_actions_target_devices(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Actions act on the targeted devices, one or several."""
    first, second = await _setup_two_devices(hass, aioclient_mock)

    aioclient_mock.mock_calls.clear()
    await hass.services.async_call(
        DOMAIN,
        "reboot",
        target={"device_id": _device_id(hass, second)},
        blocking=True,
    )
    assert reboot_calls(aioclient_mock) == [f"https://10.0.0.2{REBOOT_PATH}"]

    aioclient_mock.mock_calls.clear()
    await hass.services.async_call(
        DOMAIN,
        "reboot",
        target={"device_id": [_device_id(hass, first), _device_id(hass, second)]},
        blocking=True,
    )
    assert sorted(reboot_calls(aioclient_mock)) == [
        f"https://10.0.0.1{REBOOT_PATH}",
        f"https://10.0.0.2{REBOOT_PATH}",
    ]


async def test_actions_target_areas(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Targeting an area acts on the phones in it."""
    _, second = await _setup_two_devices(hass, aioclient_mock)
    gym = ar.async_get(hass).async_create("Gym")
    dr.async_get(hass).async_update_device(_device_id(hass, second), area_id=gym.id)
    aioclient_mock.mock_calls.clear()

    await hass.services.async_call(
        DOMAIN, "reboot", target={"area_id": gym.id}, blocking=True
    )

    assert reboot_calls(aioclient_mock) == [f"https://10.0.0.2{REBOOT_PATH}"]


async def test_actions_reject_other_devices(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
) -> None:
    """Targeting a device that isn't a Polycom phone is an error."""
    other_entry = MockConfigEntry(domain="other")
    other_entry.add_to_hass(hass)
    other = dr.async_get(hass).async_get_or_create(
        config_entry_id=other_entry.entry_id, identifiers={("other", "1")}
    )
    aioclient_mock.mock_calls.clear()

    with pytest.raises(ServiceValidationError, match="None of the chosen devices"):
        await hass.services.async_call(
            DOMAIN, "reboot", target={"device_id": other.id}, blocking=True
        )
    assert reboot_calls(aioclient_mock) == []


async def test_errors_name_the_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Errors use the name the user gave the phone's device."""
    device_id = _device_id(hass, init_integration)
    dr.async_get(hass).async_update_device(device_id, name_by_user="Gym phone")

    with pytest.raises(ServiceValidationError, match="Gym phone has no call to end"):
        await hass.services.async_call(
            DOMAIN, "end_call", target={"device_id": device_id}, blocking=True
        )
