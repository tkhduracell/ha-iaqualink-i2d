"""Constants for the iAquaLink iQPump (i2d) integration."""

from __future__ import annotations

DOMAIN = "iaqualink_i2d"

# Config / options keys
CONF_SERIAL = "serial"
CONF_DEFAULT_DURATION = "default_duration_seconds"
CONF_NORMAL_INTERVAL = "normal_interval"
CONF_FAST_INTERVAL = "fast_interval"
CONF_FAST_DURATION = "fast_duration"

# Defaults
DEFAULT_DURATION_SECONDS = 3600
DEFAULT_NORMAL_INTERVAL = 60
DEFAULT_FAST_INTERVAL = 10
DEFAULT_FAST_DURATION = 180

# RPM range fallbacks (used when the device does not report globalrpmmin/max)
DEFAULT_RPM_MIN = 1000
DEFAULT_RPM_MAX = 3450
RPM_STEP = 25

# Operating modes reported by the iQPump01 controller.
OPMODE_AUTO = 0
OPMODE_CUSTOM = 1
OPMODE_OFF = 2
OPMODE_QUICK_CLEAN = 3
OPMODE_TIMED_RUN = 4
OPMODE_TIMED_STOP = 5
OPMODE_SERVICE = 7  # remote control not authorized

# Human labels for the operating-mode sensor, aligned with the iQPump01 UI.
OPMODE_LABELS: dict[str, str] = {
    "0": "auto",
    "1": "custom",
    "2": "off",
    "3": "quick clean",
    "4": "timed run",
    "5": "timed stop",
    "7": "off",
}

# Selectable manual-speed durations, mirroring the iAquaLink app (up to ~23h59).
DURATION_OPTIONS: dict[str, int] = {
    "30 min": 1800,
    "1 h": 3600,
    "6 h": 21600,
    "12 h": 43200,
    "23 h 59": 86340,
}

# Services
SERVICE_SET_CUSTOM_SPEED = "set_custom_speed"
SERVICE_RETURN_TO_SCHEDULE = "return_to_schedule"
ATTR_RPM = "rpm"
ATTR_DURATION_SECONDS = "duration_seconds"
