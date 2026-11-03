"""Data coordinator for the Advantage Air e-zone integration."""

from __future__ import annotations

import copy
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    EzoneClient,
    EzoneCommandError,
    EzoneError,
    EzoneUnsupportedError,
    deep_merge,
)
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    REFRESH_AFTER_WRITE,
)

_LOGGER = logging.getLogger(__name__)

type EzoneConfigEntry = ConfigEntry[EzoneCoordinator]


class EzoneCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the tablet and route writes through one place."""

    config_entry: EzoneConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: EzoneConfigEntry, client: EzoneClient
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.host}",
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
            request_refresh_debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=REFRESH_AFTER_WRITE.total_seconds(),
                immediate=False,
            ),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the full system document."""
        try:
            return await self.client.async_get_system_data()
        except EzoneUnsupportedError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="unsupported_firmware",
                translation_placeholders={"error": str(err)},
            ) from err
        except EzoneError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    # ------------------------------------------------------------------ writes

    async def _async_send(
        self, send: Any, payload: dict[str, Any], optimistic: dict[str, Any]
    ) -> None:
        """Send a command, apply it optimistically, then schedule a re-read."""
        try:
            await send(payload)
        except EzoneCommandError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_rejected",
                translation_placeholders={"error": str(err)},
            ) from err
        except EzoneError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        if self.data is not None:
            data = copy.deepcopy(self.data)
            deep_merge(data, optimistic)
            self.async_set_updated_data(data)
        await self.async_request_refresh()

    async def async_set_aircon(self, payload: dict[str, Any]) -> None:
        """Change aircon ``info`` / ``zones`` fields, e.g. ``{"ac1": {...}}``."""
        await self._async_send(
            self.client.async_set_aircon, payload, {"aircons": payload}
        )

    async def async_set_ac_info(self, ac_key: str, changes: dict[str, Any]) -> None:
        """Change fields of one aircon's ``info`` block."""
        await self.async_set_aircon({ac_key: {"info": changes}})

    async def async_set_zone(
        self, ac_key: str, zone_key: str, changes: dict[str, Any]
    ) -> None:
        """Change fields of one zone."""
        await self.async_set_aircon({ac_key: {"zones": {zone_key: changes}}})

    async def async_set_light(self, light_id: str, changes: dict[str, Any]) -> None:
        """Change a MyLights light."""
        body = {"id": light_id, **changes}
        await self._async_send(
            self.client.async_set_lights,
            {light_id: body},
            {"myLights": {"lights": {light_id: changes}}},
        )

    async def async_set_thing(self, thing_id: str, value: int) -> None:
        """Change a MyThings device (blind, garage door, relay, light)."""
        await self._async_send(
            self.client.async_set_things,
            {thing_id: {"id": thing_id, "value": value}},
            {"myThings": {"things": {thing_id: {"value": value}}}},
        )
