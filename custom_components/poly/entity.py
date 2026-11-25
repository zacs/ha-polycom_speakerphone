"""PolycomEntity class."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import device_mac_address
from .const import ATTRIBUTION, DOMAIN
from .coordinator import PolycomDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.helpers.entity import EntityDescription


def phone_muted(data: dict[str, Any]) -> bool | None:
    """Return the microphone mute state, shared by the switch and binary sensor."""
    communication_info = data.get("communication_info", {})
    if isinstance(communication_info, dict):
        return communication_info.get("PhoneMuteState", "False") == "True"
    return None


class PolycomEntity(CoordinatorEntity[PolycomDataUpdateCoordinator]):
    """PolycomEntity class."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PolycomDataUpdateCoordinator,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{entity_description.key}"

        device_info = coordinator.data.get("device_info", {})
        device_vendor = device_info.get("DeviceVendor", "Polycom")
        model_number = device_info.get("ModelNumber", "Unknown")
        mac_address = device_mac_address(device_info)

        # Handle firmware version from v2 API structure
        firmware = device_info.get("Firmware", {})
        if isinstance(firmware, dict):
            firmware_version = firmware.get("Application", "Unknown")
        else:
            firmware_version = device_info.get("FirmwareRelease", "Unknown")

        self._attr_device_info = DeviceInfo(
            # Phones that don't report a MAC still need a device of their own
            identifiers={(DOMAIN, mac_address or entry.entry_id)},
            connections={(CONNECTION_NETWORK_MAC, mac_address)}
            if mac_address
            else set(),
            name=f"{device_vendor} {model_number}",
            manufacturer=device_vendor,
            model=model_number,
            sw_version=firmware_version,
            configuration_url=f"https://{entry.data[CONF_HOST]}",
        )
