"""Adds config flow for Polycom Speakerphone."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_VERIFY_SSL
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    PolycomApiClient,
    PolycomApiClientAuthenticationError,
    PolycomApiClientCommunicationError,
    PolycomApiClientError,
)
from .const import DEFAULT_USERNAME, DOMAIN, LOGGER

if TYPE_CHECKING:
    from collections.abc import Mapping

PASSWORD_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD),
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): selector.TextSelector(),
        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
        vol.Optional(CONF_VERIFY_SSL, default=False): selector.BooleanSelector(),
    },
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR})

STEP_RECONFIGURE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): selector.TextSelector(),
        vol.Optional(CONF_VERIFY_SSL, default=False): selector.BooleanSelector(),
    },
)


class PolycomFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow for Polycom Speakerphone."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            device, errors = await self._async_validate(user_input)
            if device is not None:
                if mac_address := _mac_address(device):
                    await self.async_set_unique_id(mac_address)
                    # Same phone at a new address: update it instead of duplicating
                    self._abort_if_unique_id_configured(
                        updates={CONF_HOST: user_input[CONF_HOST]}
                    )
                self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})

                device_info = device["device_info"]
                device_name = device_info.get("DeviceVendor", "Polycom")
                model = device_info.get("ModelNumber", "Unknown")
                return self.async_create_entry(
                    title=f"{device_name} {model}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],  # noqa: ARG002
    ) -> ConfigFlowResult:
        """Handle the phone rejecting the stored password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Ask for the phone's new password."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            device, errors = await self._async_validate(
                {**reauth_entry.data, **user_input}
            )
            if device is not None:
                return self.async_update_reload_and_abort(
                    reauth_entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            description_placeholders={"host": reauth_entry.data[CONF_HOST]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Change the phone's address or SSL setting."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()
        if user_input is not None:
            device, errors = await self._async_validate(
                {**reconfigure_entry.data, **user_input}
            )
            if device is not None:
                mac_address = _mac_address(device)
                if mac_address and reconfigure_entry.unique_id:
                    await self.async_set_unique_id(mac_address)
                    self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    reconfigure_entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_RECONFIGURE_SCHEMA, user_input or reconfigure_entry.data
            ),
            errors=errors,
        )

    async def _async_validate(
        self, data: Mapping[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Connect to the phone, returning its details or form errors."""
        verify_ssl = data.get(CONF_VERIFY_SSL, False)
        client = PolycomApiClient(
            host=data[CONF_HOST],
            username=DEFAULT_USERNAME,
            password=data[CONF_PASSWORD],
            session=async_get_clientsession(self.hass, verify_ssl=verify_ssl),
            verify_ssl=verify_ssl,
        )
        try:
            device_info = await client.async_get_device_info()
        except PolycomApiClientAuthenticationError:
            return None, {"base": "invalid_auth"}
        except PolycomApiClientCommunicationError as exception:
            LOGGER.debug("Unable to connect to %s: %s", data[CONF_HOST], exception)
            return None, {"base": "cannot_connect"}
        except PolycomApiClientError:
            LOGGER.exception("Unexpected error connecting to %s", data[CONF_HOST])
            return None, {"base": "unknown"}

        # Only used for its MAC address, which device info also carries
        try:
            network_info = await client.async_get_network_info()
        except PolycomApiClientError:
            network_info = {}
        return {"device_info": device_info, "network_info": network_info}, {}


def _mac_address(device: dict[str, Any]) -> str | None:
    """Return the phone's MAC address in the form used for unique IDs."""
    mac_address = device["network_info"].get("MACAddress") or device["device_info"].get(
        "MACAddress"
    )
    return str(mac_address).lower() if mac_address else None
