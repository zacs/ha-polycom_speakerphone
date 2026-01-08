"""Custom types for polycom_speakerphone."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import PolycomApiClient
    from .coordinator import PolycomDataUpdateCoordinator


type PolycomConfigEntry = ConfigEntry[PolycomData]


@dataclass
class PolycomData:
    """Data for the Polycom integration."""

    client: PolycomApiClient
    coordinator: PolycomDataUpdateCoordinator
    integration: Integration
    device_info: dict
    mac_address: str
    host: str
