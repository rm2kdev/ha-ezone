"""Diagnostics for the Advantage Air e-zone integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import EzoneConfigEntry

# The tablet's "system" block holds the install location, the logo PIN, the
# names of paired phones and their push-notification tokens.
TO_REDACT = {
    CONF_HOST,
    "backupId",
    "dealerPhoneNumber",
    "deviceIds",
    "deviceIdsV2",
    "deviceNames",
    "deviceNotificationVersion",
    "latitude",
    "longitude",
    "logoPIN",
    "postCode",
    "rid",
    "tspIp",
    "uid",
    "mid",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EzoneConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(
            {"data": dict(entry.data), "options": dict(entry.options)}, TO_REDACT
        ),
        "data": async_redact_data(coordinator.data, TO_REDACT),
    }
