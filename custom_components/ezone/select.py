"""Select platform: which zone sensor drives the aircon (MyZone)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EzoneConfigEntry, EzoneCoordinator
from .entity import EzoneAcEntity

PARALLEL_UPDATES = 0

OPTION_NONE = "none"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EzoneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the MyZone select for aircons that have sensor zones."""
    coordinator = entry.runtime_data
    async_add_entities(
        EzoneMyZoneSelect(coordinator, ac_key)
        for ac_key, ac in coordinator.data.get("aircons", {}).items()
        if any(z.get("type", 0) > 0 for z in ac.get("zones", {}).values())
    )


class EzoneMyZoneSelect(EzoneAcEntity, SelectEntity):
    """Choose the MyZone (the zone whose sensor the aircon follows)."""

    _attr_translation_key = "myzone"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EzoneCoordinator, ac_key: str) -> None:
        """Initialise the select."""
        super().__init__(coordinator, ac_key, "myzone")

    def _sensor_zones(self) -> dict[int, str]:
        return {
            int(z["number"]): z.get("name") or f"Zone {z['number']}"
            for z in self._zones.values()
            if z.get("type", 0) > 0 and "number" in z
        }

    @property
    def options(self) -> list[str]:
        """Return 'none' plus the names of zones with sensors."""
        return [OPTION_NONE, *self._sensor_zones().values()]

    @property
    def current_option(self) -> str | None:
        """Return the current MyZone."""
        number = int(self._ac.get("myZone", 0))
        if number == 0:
            return OPTION_NONE
        return self._sensor_zones().get(number)

    async def async_select_option(self, option: str) -> None:
        """Set the MyZone."""
        number = 0
        if option != OPTION_NONE:
            number = next(
                n for n, name in self._sensor_zones().items() if name == option
            )
        await self.async_set_ac({"myZone": number})
