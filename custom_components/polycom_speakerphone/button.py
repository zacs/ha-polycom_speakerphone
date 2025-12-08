"""Button platform for polycom_speakerphone."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.helpers.entity import EntityCategory

from .entity import PolycomEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PolycomDataUpdateCoordinator
    from .data import PolycomConfigEntry

ENTITY_DESCRIPTIONS = (
    ButtonEntityDescription(
        key="reboot",
        name="Reboot",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: PolycomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    async_add_entities(
        PolycomButton(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
    )


class PolycomButton(PolycomEntity, ButtonEntity):
    """polycom_speakerphone Button class."""

    def __init__(
        self,
        coordinator: PolycomDataUpdateCoordinator,
        entity_description: ButtonEntityDescription,
    ) -> None:
        """Initialize the button class."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{entity_description.key}"

    async def async_press(self) -> None:
        """Handle the button press."""
        key = self.entity_description.key
        
        if key == "reboot":
            client = self.coordinator.config_entry.runtime_data.client
            await client.async_reboot()
