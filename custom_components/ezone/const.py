"""Constants for the Advantage Air e-zone integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "ezone"
MANUFACTURER: Final = "Advantage Air"

DEFAULT_PORT: Final = 2025
DEFAULT_SCAN_INTERVAL: Final = 15  # seconds
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 300
CONF_SCAN_INTERVAL: Final = "scan_interval"

# Delay before re-reading the unit after a write, so bursts of commands
# (e.g. a scene touching several zones) collapse into a single refresh.
REFRESH_AFTER_WRITE: Final = timedelta(seconds=1)

STATE_ON: Final = "on"
STATE_OFF: Final = "off"
STATE_OPEN: Final = "open"
STATE_CLOSE: Final = "close"

# Aircon "info" keys.
INFO_MYAUTO_ENABLED: Final = "myAutoModeEnabled"
INFO_MYTEMP_ENABLED: Final = "climateControlModeEnabled"
INFO_MYAUTO_HEAT_TARGET: Final = "myAutoHeatTargetTemp"
INFO_MYAUTO_COOL_TARGET: Final = "myAutoCoolTargetTemp"
INFO_MYAUTO_CURRENT_MODE: Final = "myAutoModeCurrentSetMode"
INFO_AUTOFAN_ENABLED: Final = "aaAutoFanModeEnabled"
INFO_QUIET_NIGHT_ENABLED: Final = "quietNightModeEnabled"
INFO_FRESH_AIR: Final = "freshAirStatus"

FAN_AUTO_AA: Final = "autoAA"

# Countdown timers are minutes; the official app caps them at 12 hours.
COUNTDOWN_MAX_MINUTES: Final = 720

TEMP_MIN: Final = 16
TEMP_MAX: Final = 32

# Damper positions are set in 5 % steps by the official app.
DAMPER_STEP: Final = 5

# MyThings channel types ("channelDipState").
THING_BLIND: Final = (1, 2)
THING_GARAGE: Final = (3, 10)
THING_LIGHT: Final = 4
THING_LIGHT_DIMMABLE: Final = 5
THING_RELAY: Final = 8

# Fields a stored scene may legitimately apply to an aircon. Anything else in a
# scene snapshot (name, uid, sensor flags, ...) must never be written back.
SCENE_INFO_FIELDS: Final = frozenset(
    {
        "state",
        "mode",
        "fan",
        "setTemp",
        "myZone",
        "freshAirStatus",
        INFO_MYAUTO_ENABLED,
        INFO_MYTEMP_ENABLED,
        INFO_MYAUTO_HEAT_TARGET,
        INFO_MYAUTO_COOL_TARGET,
        INFO_AUTOFAN_ENABLED,
        INFO_QUIET_NIGHT_ENABLED,
    }
)
SCENE_ZONE_FIELDS: Final = frozenset({"state", "value", "setTemp"})
