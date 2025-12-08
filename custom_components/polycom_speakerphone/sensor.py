"""Sensor platform for polycom_speakerphone."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfInformation
from homeassistant.helpers.entity import EntityCategory

from .entity import PolycomEntity

from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PolycomDataUpdateCoordinator
    from .data import PolycomConfigEntry

ENTITY_DESCRIPTIONS = (
    SensorEntityDescription(
        key="phone_state",
        name="Phone State",
        icon="mdi:phone",
    ),
    SensorEntityDescription(
        key="last_call_time",
        name="Last Call Time",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="call_duration",
        name="Call Duration",
        icon="mdi:timer-outline",
    ),
    SensorEntityDescription(
        key="phone_error",
        name="Phone Error",
        icon="mdi:alert-circle",
    ),
    SensorEntityDescription(
        key="cpu_usage",
        name="CPU Usage",
        icon="mdi:cpu-64-bit",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="memory_usage",
        name="Memory Usage",
        icon="mdi:memory",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="memory_total",
        name="Memory Total",
        icon="mdi:memory",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="last_called_number",
        name="Last Called Number",
        icon="mdi:phone-outgoing",
    ),
    SensorEntityDescription(
        key="sip_connection",
        name="SIP Connection",
        icon="mdi:lan-connect",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="uptime",
        name="Uptime",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
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
    def native_value(self) -> str | int | float | datetime | None:
        """Return the native value of the sensor."""
        data = self.coordinator.data
        key = self.entity_description.key
        
        if key == "phone_state":
            # Use pollForStatus for real-time phone state
            poll_status = data.get("poll_status", {})
            if isinstance(poll_status, dict):
                state = poll_status.get("State")
                if state:
                    return state
            # Fallback to old call_status endpoint
            call_status = data.get("call_status", {})
            if isinstance(call_status, dict):
                return call_status.get("State", "Idle")
            return "Idle"
        
        if key == "last_call_time":
            poll_status = data.get("poll_status", {})
            if isinstance(poll_status, dict):
                state_data = poll_status.get("StateData", "")
                # Parse "Time of last call 2025-08-03T10:35:57"
                if state_data and "Time of last call" in state_data:
                    try:
                        timestamp_str = state_data.split("Time of last call ")[-1].strip()
                        # Parse ISO format timestamp and make timezone-aware using HA's timezone
                        dt = datetime.fromisoformat(timestamp_str)
                        # If no timezone info, assume it's in Home Assistant's configured timezone
                        if dt.tzinfo is None:
                            dt = dt_util.as_local(dt)
                        return dt
                    except (ValueError, IndexError):
                        pass
            return None
        
        if key == "call_duration":
            poll_status = data.get("poll_status", {})
            if isinstance(poll_status, dict):
                state_data = poll_status.get("StateData", "")
                # Parse duration if available (format TBD based on active call)
                if state_data and "duration" in state_data.lower():
                    return state_data
            return None
        
        if key == "phone_error":
            poll_status = data.get("poll_status", {})
            if isinstance(poll_status, dict):
                state_data = poll_status.get("StateData", "")
                # Check if StateData contains error information
                if state_data and ("error" in state_data.lower() or "fail" in state_data.lower()):
                    return state_data
            return None
        
        if key == "cpu_usage":
            device_stats = data.get("device_stats", {})
            if isinstance(device_stats, dict):
                cpu = device_stats.get("CPU", {})
                if isinstance(cpu, dict):
                    current = cpu.get("Current")
                    if current:
                        try:
                            return float(current)
                        except (ValueError, TypeError):
                            pass
            return None
        
        if key == "memory_usage":
            device_stats = data.get("device_stats", {})
            if isinstance(device_stats, dict):
                memory = device_stats.get("Memory", {})
                if isinstance(memory, dict):
                    try:
                        total = int(memory.get("Total", 0))
                        used = int(memory.get("Used", 0))
                        if total > 0:
                            return round((used / total) * 100, 1)
                    except (ValueError, TypeError):
                        pass
            return None
        
        if key == "memory_total":
            device_stats = data.get("device_stats", {})
            if isinstance(device_stats, dict):
                memory = device_stats.get("Memory", {})
                if isinstance(memory, dict):
                    try:
                        total = int(memory.get("Total", 0))
                        # Convert bytes to MB
                        return round(total / (1024 * 1024), 1)
                    except (ValueError, TypeError):
                        pass
            return None
        
        if key == "last_called_number":
            session_stats = data.get("session_stats", {})
            if isinstance(session_stats, dict):
                return session_stats.get("LastCalledNumber")
            return None
        
        if key == "sip_connection":
            line_info = data.get("line_info", [])
            if isinstance(line_info, list) and len(line_info) > 0:
                call_servers = line_info[0].get("CallServers", [])
                if isinstance(call_servers, list) and len(call_servers) > 0:
                    working = call_servers[0].get("Working", "False")
                    return "Connected" if working == "True" else "Disconnected"
            return "Unknown"
        
        if key == "uptime":
            device_info = data.get("device_info", {})
            if isinstance(device_info, dict):
                uptime_data = device_info.get("UpTime", {})
                if isinstance(uptime_data, dict):
                    try:
                        # Convert uptime components to total seconds
                        days = int(uptime_data.get("Days", 0))
                        hours = int(uptime_data.get("Hours", 0))
                        minutes = int(uptime_data.get("Minutes", 0))
                        seconds = int(uptime_data.get("Seconds", 0))
                        
                        total_seconds = (days * 86400) + (hours * 3600) + (minutes * 60) + seconds
                        
                        # Calculate device start time by subtracting uptime from now
                        if total_seconds > 0:
                            now = dt_util.now()
                            return (now - timedelta(seconds=total_seconds)).replace(microsecond=0)
                    except (ValueError, TypeError):
                        pass
            return None
        
        return None
