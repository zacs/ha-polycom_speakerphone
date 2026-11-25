"""Actions for polycom_speakerphone."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

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

PHONE_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})
DIAL_SCHEMA = PHONE_SCHEMA.extend(
    {
        vol.Required(ATTR_NUMBER): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional(ATTR_LINE): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)


@callback
def _async_get_entry(hass: HomeAssistant, call: ServiceCall) -> PolycomConfigEntry:
    """
    Return the loaded phone an action call refers to.

    The target may be omitted when only one phone is set up, so automations
    written before the target existed keep working.
    """
    if (entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID)) is None:
        loaded = hass.config_entries.async_loaded_entries(DOMAIN)
        if len(loaded) != 1:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="config_entry_required",
            )
        return loaded[0]

    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="config_entry_not_found",
            translation_placeholders={"entry_id": entry_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="config_entry_not_loaded",
            translation_placeholders={"title": entry.title},
        )
    return entry


async def _async_send(
    entry: PolycomConfigEntry,
    command: Callable[[PolycomApiClient], Awaitable[Any]],
    translation_key: str = "action_failed",
) -> None:
    """Send a command to a phone, reporting a refusal as an error."""
    try:
        await command(entry.runtime_data.client)
    except PolycomApiClientError as exception:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key=translation_key,
            translation_placeholders={"error": str(exception)},
        ) from exception


async def _async_active_call_handle(entry: PolycomConfigEntry) -> str:
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
            translation_key="action_failed",
            translation_placeholders={"error": str(exception)},
        ) from exception
    if call is None or not call.get("CallHandle"):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_active_call",
            translation_placeholders={"title": entry.title},
        )
    return str(call["CallHandle"])


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions."""

    async def async_reboot(call: ServiceCall) -> None:
        """Reboot a phone once any active call has ended."""
        entry = _async_get_entry(hass, call)
        await _async_send(entry, lambda client: client.async_reboot(), "reboot_failed")
        LOGGER.info("Polycom device %s rebooting", entry.title)

    async def async_dial(call: ServiceCall) -> None:
        """Call a number from a phone."""
        entry = _async_get_entry(hass, call)
        await _async_send(
            entry,
            lambda client: client.async_dial(
                call.data[ATTR_NUMBER], call.data.get(ATTR_LINE)
            ),
        )
        await entry.runtime_data.coordinator.async_request_refresh()

    async def async_answer_call(call: ServiceCall) -> None:
        """Answer a phone's incoming call."""
        entry = _async_get_entry(hass, call)
        await _async_send(entry, lambda client: client.async_answer_call())
        await entry.runtime_data.coordinator.async_request_refresh()

    async def async_reject_call(call: ServiceCall) -> None:
        """Reject a phone's incoming call."""
        entry = _async_get_entry(hass, call)
        await _async_send(entry, lambda client: client.async_reject_call())
        await entry.runtime_data.coordinator.async_request_refresh()

    async def async_end_call(call: ServiceCall) -> None:
        """Hang up a phone's current call."""
        entry = _async_get_entry(hass, call)
        handle = await _async_active_call_handle(entry)
        await _async_send(entry, lambda client: client.async_end_call(handle))
        await entry.runtime_data.coordinator.async_request_refresh()

    for service, handler, schema in (
        (SERVICE_REBOOT, async_reboot, PHONE_SCHEMA),
        (SERVICE_DIAL, async_dial, DIAL_SCHEMA),
        (SERVICE_ANSWER_CALL, async_answer_call, PHONE_SCHEMA),
        (SERVICE_REJECT_CALL, async_reject_call, PHONE_SCHEMA),
        (SERVICE_END_CALL, async_end_call, PHONE_SCHEMA),
    ):
        hass.services.async_register(DOMAIN, service, handler, schema=schema)
