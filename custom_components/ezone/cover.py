"""Cover platform: zone dampers, plus MyThings blinds and garage doors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DAMPER_STEP, STATE_CLOSE, STATE_OPEN, THING_BLIND, THING_GARAGE
from .coordinator import EzoneConfigEntry, EzoneCoordinator
from .entity import EzoneEntity, EzoneZoneEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EzoneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up cover entities."""
    coordinator = entry.runtime_data
    entities: list[CoverEntity] = []
    for ac_key, ac in coordinator.data.get("aircons", {}).items():
        entities.extend(
            EzoneZoneDamper(coordinator, ac_key, zone_key)
            for zone_key, zone in ac.get("zones", {}).items()
            if zone.get("type", 0) == 0
        )
    for thing_id, thing in (
        coordinator.data.get("myThings", {}).get("things", {}).items()
    ):
        dip = thing.get("channelDipState")
        if dip in THING_BLIND:
            entities.append(
                EzoneThingCover(coordinator, thing_id, CoverDeviceClass.BLIND)
            )
        elif dip in THING_GARAGE:
            entities.append(
                EzoneThingCover(coordinator, thing_id, CoverDeviceClass.GARAGE)
            )
    async_add_entities(entities)


def _round_damper(position: int) -> int:
    """Round a requested opening to the tablet's 5 % steps (min 5 %)."""
    return max(DAMPER_STEP, min(100, DAMPER_STEP * round(position / DAMPER_STEP)))


class EzoneZoneDamper(EzoneZoneEntity, CoverEntity):
    """A percentage-controlled zone damper."""

    _attr_name = None
    _attr_translation_key = "zone_damper"
    _attr_device_class = CoverDeviceClass.DAMPER
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(
        self, coordinator: EzoneCoordinator, ac_key: str, zone_key: str
    ) -> None:
        """Initialise the damper."""
        super().__init__(coordinator, ac_key, zone_key, "damper")

    @property
    def is_closed(self) -> bool:
        """Return True when the zone is turned off."""
        return self._zone.get("state") == STATE_CLOSE

    @property
    def current_cover_position(self) -> int:
        """Return the damper opening (0 when the zone is off)."""
        if self._zone.get("state") == STATE_OPEN:
            return int(self._zone.get("value", 0))
        return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose zone configuration."""
        return {
            "zone_number": self._zone.get("number"),
            "constant_zone": self._is_constant,
            "damper_setting": self._zone.get("value"),
        }

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Turn the zone on at its last damper setting."""
        await self.async_set_zone({"state": STATE_OPEN})

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Turn the zone off."""
        await self.async_set_zone({"state": STATE_CLOSE})

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set the damper opening; 0 turns the zone off."""
        position = int(kwargs[ATTR_POSITION])
        if position <= 0:
            await self.async_set_zone({"state": STATE_CLOSE})
            return
        await self.async_set_zone(
            {"state": STATE_OPEN, "value": _round_damper(position)}
        )


class EzoneThingCover(EzoneEntity, CoverEntity):
    """A MyThings blind or garage door."""

    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(
        self,
        coordinator: EzoneCoordinator,
        thing_id: str,
        device_class: CoverDeviceClass,
    ) -> None:
        """Initialise the cover."""
        super().__init__(coordinator, f"thing-{thing_id}")
        self._id = thing_id
        self._attr_device_class = device_class
        self._attr_name = self._thing.get("name") or thing_id

    @property
    def available(self) -> bool:
        """Return if the thing is still reported."""
        return super().available and self._id in self.coordinator.data.get(
            "myThings", {}
        ).get("things", {})

    @property
    def _thing(self) -> dict[str, Any]:
        return self.coordinator.data["myThings"]["things"][self._id]

    @property
    def is_closed(self) -> bool:
        """Return True when closed."""
        return int(self._thing.get("value", 0)) == 0

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open."""
        await self.coordinator.async_set_thing(self._id, 100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close."""
        await self.coordinator.async_set_thing(self._id, 0)
