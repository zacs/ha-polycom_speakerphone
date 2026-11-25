"""Binary sensor platform for polycom_speakerphone."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from .entity import PolycomEntity, phone_muted

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .data import PolycomConfigEntry

# Coordinator-driven entities; the coordinator serializes device access
PARALLEL_UPDATES = 0


def _first_line(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first line from lineInfo, if the phone reported one."""
    line_info = data.get("line_info")
    if isinstance(line_info, list) and line_info and isinstance(line_info[0], dict):
        return line_info[0]
    return None


def _line_flag(field: str) -> Callable[[dict[str, Any]], bool | None]:
    """Build a value function for a "True"/"False" field on the first line."""

    def value_fn(data: dict[str, Any]) -> bool | None:
        if (line := _first_line(data)) is None:
            return None
        return line.get(field, "False") == "True"

    return value_fn


def _line_registered(data: dict[str, Any]) -> bool | None:
    """Return whether the first line is registered with its SIP server."""
    if (line := _first_line(data)) is None:
        return None
    return str(line.get("RegistrationStatus", "")).lower() == "registered"


def _ringing(data: dict[str, Any]) -> bool | None:
    """Return whether any call on the phone is ringing."""
    calls = data.get("calls")
    if not isinstance(calls, list):
        return None
    return any(call.get("Ringing") == "1" for call in calls)


@dataclass(frozen=True, kw_only=True)
class PolycomBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Polycom binary sensor."""

    is_on_fn: Callable[[dict[str, Any]], bool | None]
    # Whether the phone supports this sensor, judged from the first poll
    exists_fn: Callable[[dict[str, Any]], bool] = lambda _: True


ENTITY_DESCRIPTIONS: tuple[PolycomBinarySensorEntityDescription, ...] = (
    PolycomBinarySensorEntityDescription(
        key="dnd_status",
        translation_key="dnd_status",
        is_on_fn=_line_flag("DoNotDisturb"),
    ),
    PolycomBinarySensorEntityDescription(
        key="mute_status",
        translation_key="mute_status",
        is_on_fn=phone_muted,
    ),
    PolycomBinarySensorEntityDescription(
        key="line_registered",
        translation_key="line_registered",
        is_on_fn=_line_registered,
    ),
    PolycomBinarySensorEntityDescription(
        key="line_active",
        translation_key="line_active",
        is_on_fn=_line_flag("Active"),
    ),
    PolycomBinarySensorEntityDescription(
        key="ringing",
        translation_key="ringing",
        is_on_fn=_ringing,
        exists_fn=lambda data: "calls" in data,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: PolycomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        PolycomBinarySensor(
            coordinator=coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
        if entity_description.exists_fn(coordinator.data)
    )


class PolycomBinarySensor(PolycomEntity, BinarySensorEntity):
    """polycom_speakerphone Binary Sensor class."""

    entity_description: PolycomBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self.entity_description.is_on_fn(self.coordinator.data)
