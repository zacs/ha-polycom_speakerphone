"""PolycomEntity class."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import PolycomDataUpdateCoordinator


class PolycomEntity(CoordinatorEntity[PolycomDataUpdateCoordinator]):
    """PolycomEntity class."""

    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: PolycomDataUpdateCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        
        # Get device information from runtime data
        runtime_data = coordinator.config_entry.runtime_data
        device_info = runtime_data.device_info
        mac_address = runtime_data.mac_address
        host = runtime_data.host
        
        # Extract device details
        device_vendor = device_info.get("DeviceVendor", "Polycom")
        model_number = device_info.get("ModelNumber", "Unknown")
        
        # Handle firmware version from v2 API structure
        firmware = device_info.get("Firmware", {})
        if isinstance(firmware, dict):
            firmware_version = firmware.get("Application", "Unknown")
        else:
            firmware_version = device_info.get("FirmwareRelease", "Unknown")
        
        device_name = f"{device_vendor} {model_number}"
        
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, mac_address),
            },
            connections={
                (CONNECTION_NETWORK_MAC, mac_address),
            },
            name=device_name,
            manufacturer=device_vendor,
            model=model_number,
            sw_version=firmware_version,
            configuration_url=f"https://{host}",
        )
