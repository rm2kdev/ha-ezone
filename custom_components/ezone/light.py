"""Light platform: MyLights lights and MyThings light channels."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import STATE_OFF, STATE_ON, THING_LIGHT, THING_LIGHT_DIMMABLE
from .coordinator import EzoneConfigEntry, EzoneCoordinator
from .entity import EzoneEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EzoneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up lights."""
    coordinator = entry.runtime_data
    entities: list[LightEntity] = [
        EzoneLight(coordinator, light_id, dimmable=not light.get("relay"))
        for light_id, light in coordinator.data.get("myLights", {})
        .get("lights", {})
        .items()
    ]
    for thing_id, thing in (
        coordinator.data.get("myThings", {}).get("things", {}).items()
    ):
        dip = thing.get("channelDipState")
        if dip == THING_LIGHT:
            entities.append(EzoneThingLight(coordinator, thing_id, dimmable=False))
        elif dip == THING_LIGHT_DIMMABLE:
            entities.append(EzoneThingLight(coordinator, thing_id, dimmable=True))
    async_add_entities(entities)


def _to_pct(brightness: int) -> int:
    return max(1, min(100, round(brightness * 100 / 255)))


def _to_brightness(pct: Any) -> int:
    return round(int(pct or 0) * 255 / 100)


class _EzoneLightBase(EzoneEntity, LightEntity):
    """Shared colour-mode setup."""

    def _setup_modes(self, dimmable: bool) -> None:
        mode = ColorMode.BRIGHTNESS if dimmable else ColorMode.ONOFF
        self._attr_color_mode = mode
        self._attr_supported_color_modes = {mode}


class EzoneLight(_EzoneLightBase):
    """A MyLights light (relay or dimmer)."""

    def __init__(
        self, coordinator: EzoneCoordinator, light_id: str, dimmable: bool
    ) -> None:
        """Initialise the light."""
        super().__init__(coordinator, f"light-{light_id}")
        self._id = light_id
        self._attr_name = self._light.get("name") or light_id
        self._setup_modes(dimmable)

    @property
    def available(self) -> bool:
        """Return if the light is still reported."""
        return super().available and self._id in self.coordinator.data.get(
            "myLights", {}
        ).get("lights", {})

    @property
    def _light(self) -> dict[str, Any]:
        return self.coordinator.data["myLights"]["lights"][self._id]

    @property
    def is_on(self) -> bool:
        """Return True when on."""
        return self._light.get("state") == STATE_ON

    @property
    def brightness(self) -> int | None:
        """Return brightness (0-255)."""
        if self._attr_color_mode != ColorMode.BRIGHTNESS:
            return None
        return _to_brightness(self._light.get("value"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on, optionally at a brightness."""
        changes: dict[str, Any] = {"state": STATE_ON}
        if ATTR_BRIGHTNESS in kwargs and self._attr_color_mode == ColorMode.BRIGHTNESS:
            changes["value"] = _to_pct(kwargs[ATTR_BRIGHTNESS])
        await self.coordinator.async_set_light(self._id, changes)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        await self.coordinator.async_set_light(self._id, {"state": STATE_OFF})


class EzoneThingLight(_EzoneLightBase):
    """A MyThings channel wired to a light."""

    def __init__(
        self, coordinator: EzoneCoordinator, thing_id: str, dimmable: bool
    ) -> None:
        """Initialise the light."""
        super().__init__(coordinator, f"thing-{thing_id}")
        self._id = thing_id
        self._attr_name = self._thing.get("name") or thing_id
        self._setup_modes(dimmable)

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
    def is_on(self) -> bool:
        """Return True when on."""
        return int(self._thing.get("value", 0)) > 0

    @property
    def brightness(self) -> int | None:
        """Return brightness (0-255)."""
        if self._attr_color_mode != ColorMode.BRIGHTNESS:
            return None
        return _to_brightness(self._thing.get("value"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on."""
        value = 100
        if ATTR_BRIGHTNESS in kwargs and self._attr_color_mode == ColorMode.BRIGHTNESS:
            value = _to_pct(kwargs[ATTR_BRIGHTNESS])
        await self.coordinator.async_set_thing(self._id, value)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        await self.coordinator.async_set_thing(self._id, 0)
