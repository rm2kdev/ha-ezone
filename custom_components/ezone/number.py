"""Number platform: on/off countdown timers."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COUNTDOWN_MAX_MINUTES
from .coordinator import EzoneConfigEntry, EzoneCoordinator
from .entity import EzoneAcEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EzoneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up countdown timers."""
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = []
    for ac_key, ac in coordinator.data.get("aircons", {}).items():
        for field, key in (
            ("countDownToOn", "timer_on"),
            ("countDownToOff", "timer_off"),
        ):
            if field in ac["info"]:
                entities.append(EzoneCountdown(coordinator, ac_key, field, key))
    async_add_entities(entities)


class EzoneCountdown(EzoneAcEntity, NumberEntity):
    """Minutes until the aircon turns on / off (0 = timer off)."""

    _attr_native_min_value = 0
    _attr_native_max_value = COUNTDOWN_MAX_MINUTES
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator: EzoneCoordinator, ac_key: str, field: str, key: str
    ) -> None:
        """Initialise the timer."""
        super().__init__(coordinator, ac_key, key)
        self._field = field
        self._attr_translation_key = key

    @property
    def native_value(self) -> int:
        """Return minutes remaining."""
        return int(self._ac.get(self._field, 0))

    async def async_set_native_value(self, value: float) -> None:
        """Start (or with 0, cancel) the countdown."""
        minutes = max(0, min(COUNTDOWN_MAX_MINUTES, round(value)))
        await self.async_set_ac({self._field: minutes})
