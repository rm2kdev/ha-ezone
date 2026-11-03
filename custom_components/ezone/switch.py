"""Switch platform: aircon feature toggles and MyThings relays."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    INFO_AUTOFAN_ENABLED,
    INFO_FRESH_AIR,
    INFO_QUIET_NIGHT_ENABLED,
    STATE_OFF,
    STATE_ON,
    THING_RELAY,
)
from .coordinator import EzoneConfigEntry, EzoneCoordinator
from .entity import EzoneAcEntity, EzoneEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EzoneSwitchDescription(SwitchEntityDescription):
    """Describes a boolean ``info`` field exposed as a switch."""

    field: str
    on_value: Any = True
    off_value: Any = False


AC_SWITCHES: tuple[EzoneSwitchDescription, ...] = (
    EzoneSwitchDescription(
        key="quiet_night_mode",
        translation_key="quiet_night_mode",
        field=INFO_QUIET_NIGHT_ENABLED,
        entity_category=EntityCategory.CONFIG,
    ),
    EzoneSwitchDescription(
        key="myfan",
        translation_key="myfan",
        field=INFO_AUTOFAN_ENABLED,
        entity_category=EntityCategory.CONFIG,
    ),
    EzoneSwitchDescription(
        key="fresh_air",
        translation_key="fresh_air",
        field=INFO_FRESH_AIR,
        on_value=STATE_ON,
        off_value=STATE_OFF,
    ),
)


def _switch_exists(desc: EzoneSwitchDescription, info: dict[str, Any]) -> bool:
    if desc.field not in info:
        return False
    if desc.field == INFO_FRESH_AIR:
        # "none" means the unit has no fresh-air damper fitted.
        return info[INFO_FRESH_AIR] != "none"
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EzoneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = []
    for ac_key, ac in coordinator.data.get("aircons", {}).items():
        entities.extend(
            EzoneAcSwitch(coordinator, ac_key, desc)
            for desc in AC_SWITCHES
            if _switch_exists(desc, ac["info"])
        )
    entities.extend(
        EzoneThingSwitch(coordinator, thing_id)
        for thing_id, thing in coordinator.data.get("myThings", {})
        .get("things", {})
        .items()
        if thing.get("channelDipState") == THING_RELAY
    )
    async_add_entities(entities)


class EzoneAcSwitch(EzoneAcEntity, SwitchEntity):
    """Aircon feature toggle."""

    entity_description: EzoneSwitchDescription

    def __init__(
        self,
        coordinator: EzoneCoordinator,
        ac_key: str,
        description: EzoneSwitchDescription,
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, ac_key, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the state."""
        desc = self.entity_description
        return self._ac.get(desc.field) == desc.on_value

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable."""
        desc = self.entity_description
        await self.async_set_ac({desc.field: desc.on_value})

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable."""
        desc = self.entity_description
        await self.async_set_ac({desc.field: desc.off_value})


class EzoneThingSwitch(EzoneEntity, SwitchEntity):
    """A MyThings relay."""

    def __init__(self, coordinator: EzoneCoordinator, thing_id: str) -> None:
        """Initialise the relay."""
        super().__init__(coordinator, f"thing-{thing_id}")
        self._id = thing_id
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
    def is_on(self) -> bool:
        """Return True when the relay is on."""
        return int(self._thing.get("value", 0)) > 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on."""
        await self.coordinator.async_set_thing(self._id, 100)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        await self.coordinator.async_set_thing(self._id, 0)
