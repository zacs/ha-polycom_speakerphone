"""Switch platform for polycom_speakerphone."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.exceptions import HomeAssistantError

from .api import PolycomApiClientError
from .const import DOMAIN
from .entity import PolycomEntity, phone_muted

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .api import PolycomApiClient
    from .data import PolycomConfigEntry

# Send one command to the phone at a time
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class PolycomSwitchEntityDescription(SwitchEntityDescription):
    """Describes a Polycom switch."""

    is_on_fn: Callable[[dict[str, Any]], bool | None]
    set_fn: Callable[[PolycomApiClient, bool], Awaitable[Any]]


ENTITY_DESCRIPTIONS: tuple[PolycomSwitchEntityDescription, ...] = (
    PolycomSwitchEntityDescription(
        key="mute",
        translation_key="mute",
        is_on_fn=phone_muted,
        set_fn=lambda client, on: client.async_set_mute(mute=on),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: PolycomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
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

    entity_description: PolycomSwitchEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        return self.entity_description.is_on_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn the switch on."""
        await self._async_set(on=True)

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn the switch off."""
        await self._async_set(on=False)

    async def _async_set(self, *, on: bool) -> None:
        """Send the new state to the phone, then refresh."""
        try:
            await self.entity_description.set_fn(self.coordinator.client, on)
        except PolycomApiClientError as exception:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="action_failed",
                translation_placeholders={"error": str(exception)},
            ) from exception
        await self.coordinator.async_request_refresh()
