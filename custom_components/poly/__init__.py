"""
Custom integration to integrate Polycom Speakerphone with Home Assistant.

For more details about this integration, please refer to
https://github.com/zacs/ha-polycom_speakerphone
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_VERIFY_SSL, Platform
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PolycomApiClient, device_mac_address
from .const import DEFAULT_USERNAME, DOMAIN
from .coordinator import PolycomDataUpdateCoordinator
from .data import PolycomData
from .services import async_setup_services

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

    from .data import PolycomConfigEntry

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:  # noqa: ARG001
    """Set up the integration's actions, shared by all phones."""
    async_setup_services(hass)
    return True


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(
    hass: HomeAssistant,
    entry: PolycomConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, False)
    client = PolycomApiClient(
        host=entry.data[CONF_HOST],
        username=DEFAULT_USERNAME,
        password=entry.data[CONF_PASSWORD],
        session=async_get_clientsession(hass, verify_ssl=verify_ssl),
        verify_ssl=verify_ssl,
    )
    coordinator = PolycomDataUpdateCoordinator(hass, entry, client)

    # Raises ConfigEntryNotReady (retry later) or ConfigEntryAuthFailed (reauth)
    await coordinator.async_config_entry_first_refresh()

    if entry.unique_id is None:
        _async_backfill_unique_id(hass, entry, coordinator.data)

    entry.runtime_data = PolycomData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


@callback
def _async_backfill_unique_id(
    hass: HomeAssistant, entry: PolycomConfigEntry, data: dict[str, Any]
) -> None:
    """
    Give entries from earlier versions the phone's MAC as their unique ID.

    The old config flow looked for the MAC in network info, which doesn't
    include it, so its entries never got a unique ID.
    """
    if (mac_address := device_mac_address(data.get("device_info", {}))) is None:
        return
    if any(
        other.unique_id == mac_address
        for other in hass.config_entries.async_entries(DOMAIN)
    ):
        # The same phone was added twice; leave the duplicate as it is
        return
    hass.config_entries.async_update_entry(entry, unique_id=mac_address)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: PolycomConfigEntry,
) -> bool:
    """Handle removal of an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
