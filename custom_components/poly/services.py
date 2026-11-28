"""Actions for polycom_speakerphone."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import service as service_helper

from .api import PolycomApiClientError, active_call
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_LINE,
    ATTR_NUMBER,
    DOMAIN,
    LOGGER,
    SERVICE_ANSWER_CALL,
    SERVICE_DIAL,
    SERVICE_END_CALL,
    SERVICE_REBOOT,
    SERVICE_REJECT_CALL,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .api import PolycomApiClient
    from .data import PolycomConfigEntry

# Phones are chosen by device (or anything that contains devices, like an
# area). config_entry_id is still accepted for automations written for 0.2.0.
PHONE_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}).extend(
    cv.TARGET_SERVICE_FIELDS
)
DIAL_SCHEMA = PHONE_SCHEMA.extend(
    {
        vol.Required(ATTR_NUMBER): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional(ATTR_LINE): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)
TARGET_KEYS = frozenset(str(key) for key in cv.TARGET_SERVICE_FIELDS)

# Home Assistant 2026 dropped this helper's hass argument
_EXTRACT_TAKES_HASS = (
    "hass"
    in inspect.signature(service_helper.async_extract_config_entry_ids).parameters
)


def _phone_name(hass: HomeAssistant, entry: PolycomConfigEntry) -> str:
    """Return the phone's device name as the user knows it."""
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    if devices:
        return devices[0].name_by_user or devices[0].name or entry.title
    return entry.title


def _ensure_loaded(hass: HomeAssistant, entry: PolycomConfigEntry) -> None:
    """Refuse to act on a phone that isn't set up right now."""
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="config_entry_not_loaded",
            translation_placeholders={"name": _phone_name(hass, entry)},
        )


async def _async_get_entries(
    hass: HomeAssistant, call: ServiceCall
) -> list[PolycomConfigEntry]:
    """
    Return the loaded phones an action call refers to.

    The phones may be targeted as devices (or areas and the like), given by
    config_entry_id, or left out when only one phone is set up.
    """
    if (entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID)) is not None:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="config_entry_not_found",
                translation_placeholders={"entry_id": entry_id},
            )
        _ensure_loaded(hass, entry)
        return [entry]

    if TARGET_KEYS & call.data.keys():
        if _EXTRACT_TAKES_HASS:
            entry_ids = await service_helper.async_extract_config_entry_ids(hass, call)
        else:
            entry_ids = await service_helper.async_extract_config_entry_ids(call)
        entries = [
            entry
            for entry_id in sorted(entry_ids)
            if (entry := hass.config_entries.async_get_entry(entry_id)) is not None
            and entry.domain == DOMAIN
        ]
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_targeted_phone"
            )
        for entry in entries:
            _ensure_loaded(hass, entry)
        return entries

    loaded = hass.config_entries.async_loaded_entries(DOMAIN)
    if len(loaded) != 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="config_entry_required",
        )
    return loaded


async def _async_send(
    hass: HomeAssistant,
    entry: PolycomConfigEntry,
    command: Callable[[PolycomApiClient], Awaitable[Any]],
) -> None:
    """Send a command to a phone, reporting a refusal as an error."""
    try:
        await command(entry.runtime_data.client)
    except PolycomApiClientError as exception:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="command_failed",
            translation_placeholders={
                "name": _phone_name(hass, entry),
                "error": str(exception),
            },
        ) from exception


async def _async_active_call_handle(
    hass: HomeAssistant, entry: PolycomConfigEntry
) -> str:
    """Look up the handle of the phone's current call, as it is right now."""
    client = entry.runtime_data.client
    try:
        try:
            call = active_call(await client.async_get_calls())
        except PolycomApiClientError:
            call = None
        # Fall back to the older callStatus, which reports a single call
        if call is None:
            call = await client.async_get_call_status() or None
    except PolycomApiClientError as exception:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="command_failed",
            translation_placeholders={
                "name": _phone_name(hass, entry),
                "error": str(exception),
            },
        ) from exception
    if call is None or not call.get("CallHandle"):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_active_call",
            translation_placeholders={"name": _phone_name(hass, entry)},
        )
    # callStatus version 1 writes the handle as "0x4a0ae008"; version 2, which
    # the manual says endCall takes, writes it as "4a0ae008"
    return str(call["CallHandle"]).removeprefix("0x")


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions."""

    async def async_reboot(call: ServiceCall) -> None:
        """Reboot phones once any active call has ended."""
        for entry in await _async_get_entries(hass, call):
            await _async_send(hass, entry, lambda client: client.async_reboot())
            LOGGER.info("Polycom device %s rebooting", _phone_name(hass, entry))

    async def async_dial(call: ServiceCall) -> None:
        """Call a number from phones."""
        for entry in await _async_get_entries(hass, call):
            await _async_send(
                hass,
                entry,
                lambda client: client.async_dial(
                    call.data[ATTR_NUMBER], call.data.get(ATTR_LINE)
                ),
            )
            await entry.runtime_data.coordinator.async_request_refresh()

    async def async_answer_call(call: ServiceCall) -> None:
        """Answer phones' incoming calls."""
        for entry in await _async_get_entries(hass, call):
            await _async_send(hass, entry, lambda client: client.async_answer_call())
            await entry.runtime_data.coordinator.async_request_refresh()

    async def async_reject_call(call: ServiceCall) -> None:
        """Reject phones' incoming calls."""
        for entry in await _async_get_entries(hass, call):
            await _async_send(hass, entry, lambda client: client.async_reject_call())
            await entry.runtime_data.coordinator.async_request_refresh()

    async def async_end_call(call: ServiceCall) -> None:
        """Hang up phones' current calls."""
        for entry in await _async_get_entries(hass, call):
            handle = await _async_active_call_handle(hass, entry)
            await _async_send(
                hass,
                entry,
                lambda client, handle=handle: client.async_end_call(handle),
            )
            await entry.runtime_data.coordinator.async_request_refresh()

    for service, handler, schema in (
        (SERVICE_REBOOT, async_reboot, PHONE_SCHEMA),
        (SERVICE_DIAL, async_dial, DIAL_SCHEMA),
        (SERVICE_ANSWER_CALL, async_answer_call, PHONE_SCHEMA),
        (SERVICE_REJECT_CALL, async_reject_call, PHONE_SCHEMA),
        (SERVICE_END_CALL, async_end_call, PHONE_SCHEMA),
    ):
        hass.services.async_register(DOMAIN, service, handler, schema=schema)
