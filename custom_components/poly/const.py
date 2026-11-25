"""Constants for polycom_speakerphone."""

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "poly"
ATTRIBUTION = "Data provided by Polycom Trio 8800 REST API"

# Default username for Polycom devices
DEFAULT_USERNAME = "Polycom"

SCAN_INTERVAL = timedelta(seconds=30)

# Services
SERVICE_REBOOT = "reboot"
SERVICE_DIAL = "dial"
SERVICE_ANSWER_CALL = "answer_call"
SERVICE_REJECT_CALL = "reject_call"
SERVICE_END_CALL = "end_call"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_NUMBER = "number"
ATTR_LINE = "line"
