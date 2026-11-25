"""Button platform for polycom_speakerphone."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .api import PolycomApiClientError
from .const import DOMAIN
from .entity import PolycomEntity

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .api import PolycomApiClient
    from .data import PolycomConfigEntry

# Send one command to the phone at a time
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class PolycomButtonEntityDescription(ButtonEntityDescription):
    """Describes a Polycom button."""

    press_fn: Callable[[PolycomApiClient], Awaitable[Any]]


ENTITY_DESCRIPTIONS: tuple[PolycomButtonEntityDescription, ...] = (
    PolycomButtonEntityDescription(
        key="reboot",
        translation_key="reboot",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.DIAGNOSTIC,
        press_fn=lambda client: client.async_reboot(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: PolycomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
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

    entity_description: PolycomButtonEntityDescription

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.entity_description.press_fn(self.coordinator.client)
        except PolycomApiClientError as exception:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="action_failed",
                translation_placeholders={"error": str(exception)},
            ) from exception
