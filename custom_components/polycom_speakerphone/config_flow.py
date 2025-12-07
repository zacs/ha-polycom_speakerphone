"""Adds config flow for Polycom Speakerphone."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import (
    PolycomApiClient,
    PolycomApiClientAuthenticationError,
    PolycomApiClientCommunicationError,
    PolycomApiClientError,
)
from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_VERIFY_SSL,
    DEFAULT_USERNAME,
    DOMAIN,
    LOGGER,
)


class PolycomFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Polycom Speakerphone."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        _errors = {}
        if user_input is not None:
            try:
                device_info = await self._test_connection(
                    host=user_input[CONF_HOST],
                    password=user_input[CONF_PASSWORD],
                    verify_ssl=user_input.get(CONF_VERIFY_SSL, False),
                )
            except PolycomApiClientAuthenticationError as exception:
                LOGGER.warning(exception)
                _errors["base"] = "auth"
            except PolycomApiClientCommunicationError as exception:
                LOGGER.error(exception)
                _errors["base"] = "connection"
            except PolycomApiClientError as exception:
                LOGGER.exception(exception)
                _errors["base"] = "unknown"
            else:
                # Use MAC address as unique_id
                mac_address = device_info.get("network_info", {}).get("MacAddress", "")
                if mac_address:
                    await self.async_set_unique_id(mac_address.lower())
                    self._abort_if_unique_id_configured()
                
                # Get device name for title
                device_name = device_info.get("device_info", {}).get("DeviceVendor", "Polycom")
                model = device_info.get("device_info", {}).get("ModelNumber", "Unknown")
                title = f"{device_name} {model}"
                
                return self.async_create_entry(
                    title=title,
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=(user_input or {}).get(CONF_HOST, vol.UNDEFINED),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                        ),
                    ),
                    vol.Required(
                        CONF_PASSWORD,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    ),
                    vol.Optional(
                        CONF_VERIFY_SSL,
                        default=(user_input or {}).get(CONF_VERIFY_SSL, False),
                    ): selector.BooleanSelector(),
                },
            ),
            errors=_errors,
        )

    async def _test_connection(self, host: str, password: str, verify_ssl: bool) -> dict:
        """Validate the connection to the device."""
        client = PolycomApiClient(
            host=host,
            username=DEFAULT_USERNAME,
            password=password,
            session=async_create_clientsession(self.hass, verify_ssl=verify_ssl),
            verify_ssl=verify_ssl,
        )
        # Get device and network info to validate connection and get MAC
        device_info = await client.async_get_device_info()
        network_info = await client.async_get_network_info()
        return {"device_info": device_info, "network_info": network_info}
