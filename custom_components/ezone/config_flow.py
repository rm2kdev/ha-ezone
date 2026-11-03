"""Config flow for the Advantage Air e-zone integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .api import EzoneClient, EzoneConnectionError, EzoneError, EzoneUnsupportedError
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

PORT_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
)


def _schema(host: str = "", port: int = DEFAULT_PORT) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=host): str,
            vol.Required(CONF_PORT, default=port): PORT_SELECTOR,
        }
    )


async def _async_probe(hass: HomeAssistant, host: str, port: int) -> dict[str, Any]:
    """Read the system document, raising EzoneError subclasses on failure."""
    client = EzoneClient(async_get_clientsession(hass), host, port)
    return await client.async_get_system_data()


def _unique_id(data: dict[str, Any], host: str, port: int) -> str:
    """Pick a stable id for the tablet: its cloud registration id if it has one."""
    system = data.get("system", {})
    return str(system.get("rid") or f"{host}:{port}")


class EzoneConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for e-zone."""

    VERSION = 1

    async def _async_validate(
        self, user_input: dict[str, Any], errors: dict[str, str]
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        host = user_input[CONF_HOST].strip()
        port = int(user_input[CONF_PORT])
        try:
            data = await _async_probe(self.hass, host, port)
        except EzoneUnsupportedError:
            errors["base"] = "unsupported_firmware"
        except EzoneConnectionError:
            errors["base"] = "cannot_connect"
        except EzoneError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error probing %s:%s", host, port)
            errors["base"] = "unknown"
        else:
            if not data.get("aircons"):
                errors["base"] = "no_aircons"
                return None
            return data, {CONF_HOST: host, CONF_PORT: port}
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the tablet's address."""
        errors: dict[str, str] = {}
        if user_input is not None and (
            result := await self._async_validate(user_input, errors)
        ):
            data, conf = result
            await self.async_set_unique_id(
                _unique_id(data, conf[CONF_HOST], conf[CONF_PORT])
            )
            self._abort_if_unique_id_configured(updates=conf)
            title = data["system"].get("name") or "e-zone"
            return self.async_create_entry(title=title, data=conf)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(_schema(), user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the tablet's address (e.g. after a DHCP change)."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None and (
            result := await self._async_validate(user_input, errors)
        ):
            data, conf = result
            await self.async_set_unique_id(
                _unique_id(data, conf[CONF_HOST], conf[CONF_PORT])
            )
            self._abort_if_unique_id_mismatch(reason="wrong_device")
            return self.async_update_reload_and_abort(entry, data_updates=conf)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(
                entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT)
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return EzoneOptionsFlow()


class EzoneOptionsFlow(OptionsFlow):
    """Polling options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=1,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )
