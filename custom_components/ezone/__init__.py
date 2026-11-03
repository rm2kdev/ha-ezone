"""The Advantage Air e-zone integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EzoneClient
from .const import DEFAULT_PORT
from .coordinator import EzoneConfigEntry, EzoneCoordinator
from .entity import ac_device_info, hub_device_info, zone_device_info

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: EzoneConfigEntry) -> bool:
    """Set up an e-zone tablet from a config entry."""
    client = EzoneClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
    )
    coordinator = EzoneCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Register devices parent-first so via_device links always resolve,
    # whichever platform happens to set up first.
    device_registry = dr.async_get(hass)
    device_infos = [hub_device_info(coordinator)]
    for ac_key, ac in coordinator.data.get("aircons", {}).items():
        device_infos.append(ac_device_info(coordinator, ac_key))
        device_infos.extend(
            zone_device_info(coordinator, ac_key, zone_key)
            for zone_key in ac.get("zones", {})
        )
    for info in device_infos:
        device_registry.async_get_or_create(config_entry_id=entry.entry_id, **info)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: EzoneConfigEntry) -> None:
    """Reload when options (poll interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EzoneConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
