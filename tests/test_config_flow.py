"""Tests for the Polycom Speakerphone config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from aiohttp import ClientError
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_VERIFY_SSL
from homeassistant.data_entry_flow import FlowResultType

from custom_components.poly.const import DOMAIN

from .conftest import HOST, MAC, PASSWORD, RawBody, load_data, mock_device

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

USER_INPUT = {CONF_HOST: HOST, CONF_PASSWORD: PASSWORD, CONF_VERIFY_SSL: False}


async def test_user_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A reachable phone with the right password creates an entry."""
    mock_device(aioclient_mock)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Polycom Trio 8800"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == MAC


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (401, "invalid_auth"),
        # The phone answers 403 to a request made while it's busy with another
        (403, "cannot_connect"),
        (RawBody({"Status": "4010"}), "default_password"),
        (ClientError(), "cannot_connect"),
        (TimeoutError(), "cannot_connect"),
        (500, "cannot_connect"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    error: Exception | int,
    expected: str,
) -> None:
    """Connection problems are shown on the form, and the user can retry."""
    mock_device(aioclient_mock, device_info=error)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}

    aioclient_mock.clear_requests()
    mock_device(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_unexpected_payload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A response that isn't JSON is reported as an unknown error."""
    aioclient_mock.get(f"https://{HOST}/api/v2/mgmt/device/info", text="<html>")
    mock_device(aioclient_mock)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] in {"cannot_connect", "unknown"}


async def test_user_flow_device_error_status(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An error Status in an HTTP 200 reply isn't mistaken for success."""
    mock_device(aioclient_mock, device_info=RawBody({"Status": "5000"}))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Adding the same phone again aborts, and picks up its new address."""
    mock_config_entry.add_to_hass(hass)
    mock_device(aioclient_mock, host="192.168.1.99")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_HOST: "192.168.1.99"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_HOST] == "192.168.1.99"


async def test_user_flow_does_not_need_network_info(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The MAC comes from device info; network info isn't requested at all."""
    mock_device(aioclient_mock)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert not any("network/info" in str(c[1]) for c in aioclient_mock.mock_calls)


async def test_user_flow_without_mac_dedupes_by_host(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A phone that reports no MAC still can't be added twice at one address."""
    device_info = load_data("device_info")
    del device_info["MACAddress"]
    mock_device(aioclient_mock, device_info=device_info)

    for expected in (FlowResultType.CREATE_ENTRY, FlowResultType.ABORT):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        assert result["type"] is expected


async def test_reauth_flow(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
) -> None:
    """A new password can be entered when the old one stops working."""
    result = await init_integration.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    aioclient_mock.clear_requests()
    mock_device(aioclient_mock, device_info=401)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    mock_device(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert init_integration.data[CONF_PASSWORD] == "new-password"
    assert init_integration.data[CONF_HOST] == HOST


async def test_reconfigure_flow(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
) -> None:
    """The phone's address can be changed without removing it."""
    result = await init_integration.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    mock_device(aioclient_mock, host="192.168.1.77")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.77", CONF_VERIFY_SSL: False}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert init_integration.data[CONF_HOST] == "192.168.1.77"
    assert init_integration.data[CONF_PASSWORD] == PASSWORD


async def test_reconfigure_flow_wrong_device(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
) -> None:
    """Pointing an entry at a different phone is refused."""
    result = await init_integration.start_reconfigure_flow(hass)

    mock_device(
        aioclient_mock,
        host="192.168.1.77",
        device_info={**load_data("device_info"), "MACAddress": "64167fabcdef"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.77", CONF_VERIFY_SSL: False}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert init_integration.data[CONF_HOST] == HOST
