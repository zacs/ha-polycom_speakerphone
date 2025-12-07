"""Constants for polycom_speakerphone."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "polycom_speakerphone"
ATTRIBUTION = "Data provided by Polycom Trio 8800 REST API"

# Configuration
CONF_HOST = "host"
CONF_VERIFY_SSL = "verify_ssl"

# Services
SERVICE_REBOOT = "reboot"
SERVICE_SET_DND = "set_dnd"
SERVICE_SET_VOLUME = "set_volume"
