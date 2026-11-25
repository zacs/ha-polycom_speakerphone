"""Sensor platform for polycom_speakerphone."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfInformation
from homeassistant.core import callback
from homeassistant.util import dt as dt_util

from .entity import PolycomEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from homeassistant.helpers.typing import StateType

    from .coordinator import PolycomDataUpdateCoordinator
    from .data import PolycomConfigEntry

# Coordinator-driven entities; the coordinator serializes device access
PARALLEL_UPDATES = 0

# The computed boot time drifts by a second or two between polls because
# uptime is reported in whole seconds; ignore changes smaller than this.
UPTIME_TOLERANCE = timedelta(minutes=1)


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a dict-valued section of the coordinator data, or an empty dict."""
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _state_data(data: dict[str, Any], state: str) -> str | None:
    """
    Return pollForStatus StateData while the phone is in the given State.

    Per Poly's REST API reference, StateData holds the time of the last call
    while "Idle", the call duration while "Active", and error text while
    "Error".
    """
    poll_status = _section(data, "poll_status")
    state_data = poll_status.get("StateData")
    if poll_status.get("State") != state or not isinstance(state_data, str):
        return None
    return state_data


def _phone_state(data: dict[str, Any]) -> str:
    """Prefer pollForStatus for real-time state; fall back to callStatus."""
    if state := _section(data, "poll_status").get("State"):
        return state
    return _section(data, "call_status").get("CallState", "Idle")


def _last_call_time(data: dict[str, Any]) -> datetime | None:
    """Parse 'Time of last call 2025-08-03T10:35:57' from StateData."""
    state_data = _state_data(data, "Idle")
    if state_data is None or "Time of last call" not in state_data:
        return None
    try:
        last_call = datetime.fromisoformat(
            state_data.split("Time of last call ")[-1].strip()
        )
    except ValueError:
        return None
    # The phone reports its local time without an offset
    if last_call.tzinfo is None:
        last_call = last_call.replace(tzinfo=dt_util.get_default_time_zone())
    return last_call


def _call_duration(data: dict[str, Any]) -> str | None:
    """Return the active call's duration, as the phone formats it."""
    return _state_data(data, "Active")


def _phone_error(data: dict[str, Any]) -> str | None:
    """Return the phone's error text, e.g. "All Phone applications are not ready"."""
    return _state_data(data, "Error")


def _cpu_usage(data: dict[str, Any]) -> float | None:
    """Return current CPU utilization."""
    cpu = _section(_section(data, "device_stats"), "CPU")
    if current := cpu.get("Current"):
        try:
            return float(current)
        except (ValueError, TypeError):
            pass
    return None


def _memory(data: dict[str, Any]) -> dict[str, Any]:
    """Return the memory section of the device stats."""
    return _section(_section(data, "device_stats"), "Memory")


def _memory_usage(data: dict[str, Any]) -> float | None:
    """Return used memory as a percentage of total."""
    memory = _memory(data)
    try:
        total = int(memory.get("Total", 0))
        used = int(memory.get("Used", 0))
    except (ValueError, TypeError):
        return None
    if total > 0:
        return round((used / total) * 100, 1)
    return None


def _memory_total(data: dict[str, Any]) -> float | None:
    """Return total memory, converted from bytes to MiB."""
    try:
        total = int(_memory(data).get("Total", 0))
    except (ValueError, TypeError):
        return None
    return round(total / (1024 * 1024), 1)


def _sip_connection(data: dict[str, Any]) -> str:
    """Return whether the first line's call server is working."""
    line_info = data.get("line_info")
    if isinstance(line_info, list) and line_info and isinstance(line_info[0], dict):
        call_servers = line_info[0].get("CallServers")
        if (
            isinstance(call_servers, list)
            and call_servers
            and isinstance(call_servers[0], dict)
        ):
            working = call_servers[0].get("Working", "False")
            return "Connected" if working == "True" else "Disconnected"
    return "Unknown"


def _boot_time(data: dict[str, Any]) -> datetime | None:
    """Return when the device last started, from its reported uptime."""
    uptime = _section(_section(data, "device_info"), "UpTime")
    try:
        total_seconds = (
            int(uptime.get("Days", 0)) * 86400
            + int(uptime.get("Hours", 0)) * 3600
            + int(uptime.get("Minutes", 0)) * 60
            + int(uptime.get("Seconds", 0))
        )
    except (ValueError, TypeError):
        return None
    if total_seconds <= 0:
        return None
    return (dt_util.now() - timedelta(seconds=total_seconds)).replace(microsecond=0)


@dataclass(frozen=True, kw_only=True)
class PolycomSensorEntityDescription(SensorEntityDescription):
    """Describes a Polycom sensor."""

    value_fn: Callable[[dict[str, Any]], StateType | datetime]


ENTITY_DESCRIPTIONS: tuple[PolycomSensorEntityDescription, ...] = (
    PolycomSensorEntityDescription(
        key="phone_state",
        translation_key="phone_state",
        value_fn=_phone_state,
    ),
    PolycomSensorEntityDescription(
        key="last_call_time",
        translation_key="last_call_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_call_time,
    ),
    PolycomSensorEntityDescription(
        key="call_duration",
        translation_key="call_duration",
        value_fn=_call_duration,
    ),
    PolycomSensorEntityDescription(
        key="phone_error",
        translation_key="phone_error",
        value_fn=_phone_error,
    ),
    PolycomSensorEntityDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_cpu_usage,
    ),
    PolycomSensorEntityDescription(
        key="memory_usage",
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_memory_usage,
    ),
    PolycomSensorEntityDescription(
        key="memory_total",
        translation_key="memory_total",
        native_unit_of_measurement=UnitOfInformation.MEBIBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_memory_total,
    ),
    PolycomSensorEntityDescription(
        key="last_called_number",
        translation_key="last_called_number",
        value_fn=lambda data: _section(data, "session_stats").get("LastCalledNumber"),
    ),
    PolycomSensorEntityDescription(
        key="sip_connection",
        translation_key="sip_connection",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_sip_connection,
    ),
    PolycomSensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_boot_time,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: PolycomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        (PolycomUptimeSensor if description.key == "uptime" else PolycomSensor)(
            coordinator=coordinator,
            entity_description=description,
        )
        for description in ENTITY_DESCRIPTIONS
    )


class PolycomSensor(PolycomEntity, SensorEntity):
    """polycom_speakerphone Sensor class."""

    entity_description: PolycomSensorEntityDescription

    @property
    def native_value(self) -> StateType | datetime:
        """Return the native value of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)


class PolycomUptimeSensor(PolycomSensor):
    """Boot time sensor that ignores sub-minute drift between polls."""

    def __init__(
        self,
        coordinator: PolycomDataUpdateCoordinator,
        entity_description: PolycomSensorEntityDescription,
    ) -> None:
        """Initialize the sensor with the boot time from the first poll."""
        super().__init__(coordinator, entity_description)
        self._boot_time = self._fetch_boot_time()

    def _fetch_boot_time(self) -> datetime | None:
        """Compute the boot time from the latest coordinator data."""
        value = self.entity_description.value_fn(self.coordinator.data)
        return value if isinstance(value, datetime) else None

    @property
    def native_value(self) -> datetime | None:
        """Return the device boot time."""
        return self._boot_time

    @callback
    def _handle_coordinator_update(self) -> None:
        """Only move the boot time when it changed meaningfully (a reboot)."""
        # After a failed poll the data is stale, so the computed time would drift
        if self.coordinator.last_update_success:
            new = self._fetch_boot_time()
            if (
                new is None
                or self._boot_time is None
                or abs(new - self._boot_time) > UPTIME_TOLERANCE
            ):
                self._boot_time = new
        super()._handle_coordinator_update()
