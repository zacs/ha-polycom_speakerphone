"""
Custom integration to integrate Polycom Speakerphone with Home Assistant.

For more details about this integration, please refer to
https://github.com/zacs/ha-polycom_speakerphone
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.core import ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_loaded_integration

from .api import PolycomApiClient
from .const import (
    CONF_HOST,
    CONF_VERIFY_SSL,
    DOMAIN,
    LOGGER,
    SERVICE_REBOOT,
    SERVICE_SET_DND,
    SERVICE_SET_VOLUME,
)
from .coordinator import PolycomDataUpdateCoordinator
from .data import PolycomData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import PolycomConfigEntry

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
]

# Service schemas
SERVICE_SET_DND_SCHEMA = vol.Schema({
    vol.Required("enabled"): cv.boolean,
})

SERVICE_SET_VOLUME_SCHEMA = vol.Schema({
    vol.Required("volume"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
})


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(
    hass: HomeAssistant,
    entry: PolycomConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    # Create API client
    client = PolycomApiClient(
        host=entry.data[CONF_HOST],
        session=async_get_clientsession(hass, verify_ssl=entry.data.get(CONF_VERIFY_SSL, True)),
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, True),
    )
    
    # Get initial device info
    device_info = await client.async_get_device_info()
    network_info = await client.async_get_network_info()
    mac_address = network_info.get("MacAddress", "").lower()
    
    # Create coordinator
    coordinator = PolycomDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name=DOMAIN,
        update_interval=timedelta(seconds=30),
    )
    
    entry.runtime_data = PolycomData(
        client=client,
        integration=async_get_loaded_integration(hass, entry.domain),
        coordinator=coordinator,
        device_info=device_info,
        mac_address=mac_address,
    )

    # https://developers.home-assistant.io/docs/integration_fetching_data#coordinated-single-api-poll-for-data-for-all-entities
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    
    # Register services
    async def handle_reboot(call: ServiceCall) -> None:
        """Handle the reboot service call."""
        await client.async_reboot()
        LOGGER.info("Polycom device rebooting")
    
    async def handle_set_dnd(call: ServiceCall) -> None:
        """Handle the set DND service call."""
        enabled = call.data["enabled"]
        await client.async_set_dnd(enabled)
        await coordinator.async_request_refresh()
    
    async def handle_set_volume(call: ServiceCall) -> None:
        """Handle the set volume service call."""
        volume = call.data["volume"]
        await client.async_set_volume(volume)
        await coordinator.async_request_refresh()
    
    hass.services.async_register(
        DOMAIN, SERVICE_REBOOT, handle_reboot
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_DND, handle_set_dnd, schema=SERVICE_SET_DND_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_VOLUME, handle_set_volume, schema=SERVICE_SET_VOLUME_SCHEMA
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: PolycomConfigEntry,
) -> bool:
    """Handle removal of an entry."""
    # Unregister services
    hass.services.async_remove(DOMAIN, SERVICE_REBOOT)
    hass.services.async_remove(DOMAIN, SERVICE_SET_DND)
    hass.services.async_remove(DOMAIN, SERVICE_SET_VOLUME)
    
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant,
    entry: PolycomConfigEntry,
) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
