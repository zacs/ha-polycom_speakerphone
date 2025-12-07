"""Sensor platform for polycom_speakerphone."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfInformation

from .entity import PolycomEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PolycomDataUpdateCoordinator
    from .data import PolycomConfigEntry

ENTITY_DESCRIPTIONS = (
    SensorEntityDescription(
        key="call_state",
        name="Call State",
        icon="mdi:phone",
    ),
    SensorEntityDescription(
        key="cpu_usage",
        name="CPU Usage",
        icon="mdi:cpu-64-bit",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="memory_usage",
        name="Memory Usage",
        icon="mdi:memory",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="memory_total",
        name="Memory Total",
        icon="mdi:memory",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
    ),
    SensorEntityDescription(
        key="line_state",
        name="Line State",
        icon="mdi:phone-check",
    ),
    SensorEntityDescription(
        key="last_called_number",
        name="Last Called Number",
        icon="mdi:phone-outgoing",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: PolycomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    async_add_entities(
        PolycomSensor(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
    )


class PolycomSensor(PolycomEntity, SensorEntity):
    """polycom_speakerphone Sensor class."""

    def __init__(
        self,
        coordinator: PolycomDataUpdateCoordinator,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor class."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{entity_description.key}"

    @property
    def native_value(self) -> str | int | float | None:
        """Return the native value of the sensor."""
        data = self.coordinator.data
        key = self.entity_description.key
        
        if key == "call_state":
            call_status = data.get("call_status", {})
            if isinstance(call_status, dict):
                return call_status.get("State", "Idle")
            return "Unknown"
        
        if key == "cpu_usage":
            device_stats = data.get("device_stats", {})
            if isinstance(device_stats, dict):
                cpu = device_stats.get("CPU", {})
                if isinstance(cpu, dict):
                    return cpu.get("Usage")
            return None
        
        if key == "memory_usage":
            device_stats = data.get("device_stats", {})
            if isinstance(device_stats, dict):
                memory = device_stats.get("Memory", {})
                if isinstance(memory, dict):
                    total = memory.get("Total", 0)
                    free = memory.get("Free", 0)
                    if total > 0:
                        used = total - free
                        return round((used / total) * 100, 1)
            return None
        
        if key == "memory_total":
            device_stats = data.get("device_stats", {})
            if isinstance(device_stats, dict):
                memory = device_stats.get("Memory", {})
                if isinstance(memory, dict):
                    return memory.get("Total")
            return None
        
        if key == "line_state":
            line_info = data.get("line_info", {})
            if isinstance(line_info, dict):
                lines = line_info.get("Lines", [])
                if lines and len(lines) > 0:
                    return lines[0].get("RegistrationState", "Unknown")
            return "Unknown"
        
        if key == "last_called_number":
            session_stats = data.get("session_stats", {})
            if isinstance(session_stats, dict):
                return session_stats.get("LastNumber")
            return None
        
        return None
