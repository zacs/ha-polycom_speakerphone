"""Switch platform for polycom_speakerphone."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription

from .entity import PolycomEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PolycomDataUpdateCoordinator
    from .data import PolycomConfigEntry

ENTITY_DESCRIPTIONS = (
    SwitchEntityDescription(
        key="mute",
        name="Mute",
        icon="mdi:microphone-off",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: PolycomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    async_add_entities(
        PolycomSwitch(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
    )


class PolycomSwitch(PolycomEntity, SwitchEntity):
    """polycom_speakerphone Switch class."""

    def __init__(
        self,
        coordinator: PolycomDataUpdateCoordinator,
        entity_description: SwitchEntityDescription,
    ) -> None:
        """Initialize the switch class."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{entity_description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        data = self.coordinator.data
        key = self.entity_description.key
        
        if key == "mute":
            communication_info = data.get("communication_info", {})
            if isinstance(communication_info, dict):
                mute_state = communication_info.get("PhoneMuteState", "False")
                return mute_state == "True"
            return None
        
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        key = self.entity_description.key
        
        if key == "mute":
            client = self.coordinator.config_entry.runtime_data.client
            await client.async_set_mute(True)
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        key = self.entity_description.key
        
        if key == "mute":
            client = self.coordinator.config_entry.runtime_data.client
            await client.async_set_mute(False)
            await self.coordinator.async_request_refresh()
