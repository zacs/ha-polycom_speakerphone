"""Binary sensor platform for polycom_speakerphone."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from .entity import PolycomEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PolycomDataUpdateCoordinator
    from .data import PolycomConfigEntry

ENTITY_DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="dnd_status",
        name="Do Not Disturb",
        icon="mdi:phone-off",
    ),
    BinarySensorEntityDescription(
        key="mute_status",
        name="Muted",
        icon="mdi:microphone-off",
    ),
    BinarySensorEntityDescription(
        key="line_registered",
        name="Line Registered",
        icon="mdi:phone-check",
    ),
    BinarySensorEntityDescription(
        key="line_active",
        name="Line Active",
        icon="mdi:phone-check",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: PolycomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    async_add_entities(
        PolycomBinarySensor(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
    )


class PolycomBinarySensor(PolycomEntity, BinarySensorEntity):
    """polycom_speakerphone Binary Sensor class."""

    def __init__(
        self,
        coordinator: PolycomDataUpdateCoordinator,
        entity_description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor class."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{entity_description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        data = self.coordinator.data
        key = self.entity_description.key
        
        if key == "dnd_status":
            line_info = data.get("line_info", [])
            if isinstance(line_info, list) and len(line_info) > 0:
                dnd = line_info[0].get("DoNotDisturb", "False")
                return dnd == "True"
            return None
        
        if key == "mute_status":
            communication_info = data.get("communication_info", {})
            if isinstance(communication_info, dict):
                mute_state = communication_info.get("PhoneMuteState", "False")
                return mute_state == "True"
            return None
        
        if key == "line_registered":
            line_info = data.get("line_info", [])
            if isinstance(line_info, list) and len(line_info) > 0:
                reg_status = line_info[0].get("RegistrationStatus", "")
                return reg_status.lower() == "registered"
            return None
        
        if key == "line_active":
            line_info = data.get("line_info", [])
            if isinstance(line_info, list) and len(line_info) > 0:
                active = line_info[0].get("Active", "False")
                return active == "True"
            return None
        
        return None
