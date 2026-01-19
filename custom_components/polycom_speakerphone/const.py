"""Constants for polycom_speakerphone."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "poly"
ATTRIBUTION = "Data provided by Polycom Trio 8800 REST API"

# Configuration
CONF_HOST = "host"
CONF_PASSWORD = "password"
CONF_VERIFY_SSL = "verify_ssl"

# Default username for Polycom devices
DEFAULT_USERNAME = "Polycom"

# Services
SERVICE_REBOOT = "reboot"
