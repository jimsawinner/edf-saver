"""Constants for EDF Weekend Saver."""

from datetime import timedelta

DOMAIN = "edf_weekend_saver"

CONF_ENERGY_SENSOR = "energy_sensor"
CONF_UNIT_RATE = "unit_rate"

DEFAULT_NAME = "EDF Weekend Saver"
DEFAULT_UNIT_RATE = 25.0  # pence per kWh

UPDATE_INTERVAL = timedelta(minutes=5)
STORAGE_VERSION = 1

SERVICE_BOOK_FREE_HOURS = "book_free_hours"
SERVICE_CANCEL_FREE_HOURS = "cancel_free_hours"
SERVICE_SET_AWARDED_HOURS = "set_awarded_hours"

ATTR_START = "start"
ATTR_HOURS = "hours"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
