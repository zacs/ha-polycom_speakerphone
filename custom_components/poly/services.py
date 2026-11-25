"""Actions for polycom_speakerphone."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import PolycomApiClientError
from .const import ATTR_CONFIG_ENTRY_ID, DOMAIN, LOGGER, SERVICE_REBOOT

if TYPE_CHECKING:
    from .data import PolycomConfigEntry

REBOOT_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})


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


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions."""

    async def async_reboot(call: ServiceCall) -> None:
        """Reboot a phone once any active call has ended."""
        entry = _async_get_entry(hass, call)
        try:
            await entry.runtime_data.client.async_reboot()
        except PolycomApiClientError as exception:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="reboot_failed",
                translation_placeholders={"error": str(exception)},
            ) from exception
        LOGGER.info("Polycom device %s rebooting", entry.title)

    hass.services.async_register(
        DOMAIN, SERVICE_REBOOT, async_reboot, schema=REBOOT_SCHEMA
    )
