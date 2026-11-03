"""Climate platform: the aircon itself, plus zones that have temperature sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    DOMAIN,
    FAN_AUTO_AA,
    INFO_AUTOFAN_ENABLED,
    INFO_MYAUTO_COOL_TARGET,
    INFO_MYAUTO_CURRENT_MODE,
    INFO_MYAUTO_ENABLED,
    INFO_MYAUTO_HEAT_TARGET,
    INFO_MYTEMP_ENABLED,
    STATE_CLOSE,
    STATE_OFF,
    STATE_ON,
    STATE_OPEN,
    TEMP_MAX,
    TEMP_MIN,
)
from .coordinator import EzoneConfigEntry, EzoneCoordinator
from .entity import EzoneAcEntity, EzoneZoneEntity

PARALLEL_UPDATES = 0

EZONE_TO_HVAC = {
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "vent": HVACMode.FAN_ONLY,
    "dry": HVACMode.DRY,
    "myauto": HVACMode.HEAT_COOL,
}
HVAC_TO_EZONE = {v: k for k, v in EZONE_TO_HVAC.items()}

MODE_TO_ACTION = {
    "cool": HVACAction.COOLING,
    "heat": HVACAction.HEATING,
    "vent": HVACAction.FAN,
    "dry": HVACAction.DRYING,
}

FAN_MODES = [FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_AUTO]

PRESET_MYZONE = "myzone"
PRESET_MYTEMP = "mytemp"
PRESET_MYAUTO = "myauto"

BASE_FEATURES = (
    ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EzoneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up climate entities."""
    coordinator = entry.runtime_data
    entities: list[ClimateEntity] = []
    for ac_key, ac in coordinator.data.get("aircons", {}).items():
        entities.append(EzoneAircon(coordinator, ac_key))
        entities.extend(
            EzoneSensorZone(coordinator, ac_key, zone_key)
            for zone_key, zone in ac.get("zones", {}).items()
            if zone.get("type", 0) > 0
        )
    async_add_entities(entities)


class EzoneAircon(EzoneAcEntity, ClimateEntity):
    """The ducted aircon unit."""

    _attr_name = None
    _attr_translation_key = "aircon"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_TENTHS  # MyZone sensors report tenths
    _attr_target_temperature_step = PRECISION_WHOLE
    _attr_min_temp = TEMP_MIN
    _attr_max_temp = TEMP_MAX
    _attr_fan_modes = FAN_MODES

    def __init__(self, coordinator: EzoneCoordinator, ac_key: str) -> None:
        """Initialise the aircon entity."""
        super().__init__(coordinator, ac_key, "climate")
        self._configure()

    def _configure(self) -> None:
        """Derive features/presets from what the unit reports."""
        info = self._ac
        presets = [PRESET_MYZONE]
        if INFO_MYTEMP_ENABLED in info:
            presets.append(PRESET_MYTEMP)
        if INFO_MYAUTO_ENABLED in info:
            presets.append(PRESET_MYAUTO)
        self._attr_preset_modes = presets if len(presets) > 1 else None

        modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.FAN_ONLY]
        modes.append(HVACMode.DRY)
        if info.get(INFO_MYAUTO_ENABLED) or info.get("mode") == "myauto":
            modes.append(HVACMode.HEAT_COOL)
        self._attr_hvac_modes = modes

        features = BASE_FEATURES
        if self._attr_preset_modes:
            features |= ClimateEntityFeature.PRESET_MODE
        preset = self._control
        if preset == PRESET_MYAUTO and info.get("mode") == "myauto":
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        elif preset != PRESET_MYTEMP:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        self._attr_supported_features = features

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.available:
            self._configure()
        super()._handle_coordinator_update()

    # ----------------------------------------------------------------- state

    @property
    def _control(self) -> str:
        """Return the active control strategy (MyZone, MyTemp or MyAuto)."""
        if self._ac.get(INFO_MYAUTO_ENABLED):
            return PRESET_MYAUTO
        if self._ac.get(INFO_MYTEMP_ENABLED):
            return PRESET_MYTEMP
        return PRESET_MYZONE

    @property
    def preset_mode(self) -> str | None:
        """Return the active control strategy as a preset."""
        if not self._attr_preset_modes:
            return None
        return self._control

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current mode."""
        if self._ac.get("state") != STATE_ON:
            return HVACMode.OFF
        return EZONE_TO_HVAC.get(self._ac.get("mode", ""))

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return what the unit is doing."""
        if self._ac.get("state") != STATE_ON:
            return HVACAction.OFF
        mode = self._ac.get("mode")
        if mode == "myauto":
            mode = self._ac.get(INFO_MYAUTO_CURRENT_MODE)
        return MODE_TO_ACTION.get(mode or "")

    @property
    def fan_mode(self) -> str | None:
        """Return the fan speed."""
        fan = self._ac.get("fan")
        if fan == FAN_AUTO_AA:
            return FAN_AUTO
        return fan

    @property
    def current_temperature(self) -> float | None:
        """Return the MyZone sensor temperature, if one is selected."""
        if (zone := self._myzone) and zone.get("type", 0) > 0:
            return zone.get("measuredTemp")
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the set point."""
        if (
            self._control == PRESET_MYZONE
            and (zone := self._myzone)
            and zone.get("type", 0) > 0
        ):
            return zone.get("setTemp")
        return self._ac.get("setTemp")

    @property
    def target_temperature_low(self) -> float | None:
        """Return the MyAuto heating set point."""
        return self._ac.get(INFO_MYAUTO_HEAT_TARGET)

    @property
    def target_temperature_high(self) -> float | None:
        """Return the MyAuto cooling set point."""
        return self._ac.get(INFO_MYAUTO_COOL_TARGET)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose a few useful raw fields."""
        info = self._ac
        attrs: dict[str, Any] = {"my_zone": info.get("myZone", 0)}
        if info.get("airconErrorCode"):
            attrs["error_code"] = info["airconErrorCode"]
        return attrs

    # -------------------------------------------------------------- commands

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the mode (turning the unit on), or turn it off."""
        if hvac_mode == HVACMode.OFF:
            await self.async_set_ac({"state": STATE_OFF})
            return
        if hvac_mode not in self.hvac_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_hvac_mode",
                translation_placeholders={"mode": str(hvac_mode)},
            )
        await self.async_set_ac({"state": STATE_ON, "mode": HVAC_TO_EZONE[hvac_mode]})

    async def async_turn_on(self) -> None:
        """Turn the unit on in its last mode."""
        await self.async_set_ac({"state": STATE_ON})

    async def async_turn_off(self) -> None:
        """Turn the unit off."""
        await self.async_set_ac({"state": STATE_OFF})

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan speed."""
        if fan_mode == FAN_AUTO and self._ac.get(INFO_AUTOFAN_ENABLED):
            fan_mode = FAN_AUTO_AA
        await self.async_set_ac({"fan": fan_mode})

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the set point (and optionally the mode in one command)."""
        info_changes: dict[str, Any] = {}
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            if hvac_mode == HVACMode.OFF:
                info_changes["state"] = STATE_OFF
            else:
                info_changes["state"] = STATE_ON
                info_changes["mode"] = HVAC_TO_EZONE[hvac_mode]

        if ATTR_TARGET_TEMP_LOW in kwargs and ATTR_TARGET_TEMP_HIGH in kwargs:
            info_changes[INFO_MYAUTO_HEAT_TARGET] = round(kwargs[ATTR_TARGET_TEMP_LOW])
            info_changes[INFO_MYAUTO_COOL_TARGET] = round(kwargs[ATTR_TARGET_TEMP_HIGH])
        elif (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            temp = round(temp)
            zone = self._myzone
            if (
                self._control == PRESET_MYZONE
                and zone is not None
                and zone.get("type", 0) > 0
            ):
                # With a MyZone sensor active, the zone's set point drives the unit.
                payload: dict[str, Any] = {
                    "zones": {f"z{zone['number']:02d}": {"setTemp": temp}}
                }
                if info_changes:
                    payload["info"] = info_changes
                await self.coordinator.async_set_aircon({self.ac_key: payload})
                return
            info_changes["setTemp"] = temp

        if info_changes:
            await self.async_set_ac(info_changes)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Switch between MyZone, MyTemp and MyAuto control."""
        changes: dict[str, Any] = {}
        if INFO_MYTEMP_ENABLED in self._ac:
            changes[INFO_MYTEMP_ENABLED] = preset_mode == PRESET_MYTEMP
        if INFO_MYAUTO_ENABLED in self._ac:
            changes[INFO_MYAUTO_ENABLED] = preset_mode == PRESET_MYAUTO
        if changes:
            await self.async_set_ac(changes)


class EzoneSensorZone(EzoneZoneEntity, ClimateEntity):
    """A zone with its own temperature sensor (temperature-controlled damper)."""

    _attr_name = None
    _attr_translation_key = "zone"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_TENTHS
    _attr_target_temperature_step = PRECISION_WHOLE
    _attr_min_temp = TEMP_MIN
    _attr_max_temp = TEMP_MAX
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(
        self, coordinator: EzoneCoordinator, ac_key: str, zone_key: str
    ) -> None:
        """Initialise the zone climate entity."""
        super().__init__(coordinator, ac_key, zone_key, "climate")

    @property
    def hvac_mode(self) -> HVACMode:
        """Open zones follow the aircon; closed zones are off."""
        if self._zone.get("state") == STATE_OPEN:
            return HVACMode.HEAT_COOL
        return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        """Report what air this zone is getting."""
        if self._zone.get("state") != STATE_OPEN or self._ac.get("state") != STATE_ON:
            return HVACAction.OFF
        mode = self._ac.get("mode")
        if mode == "myauto":
            mode = self._ac.get(INFO_MYAUTO_CURRENT_MODE)
        if self._zone.get("value", 0) == 0:
            return HVACAction.IDLE
        return MODE_TO_ACTION.get(mode or "")

    @property
    def current_temperature(self) -> float | None:
        """Return the zone sensor reading."""
        return self._zone.get("measuredTemp")

    @property
    def target_temperature(self) -> float | None:
        """Return the zone set point."""
        return self._zone.get("setTemp")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the damper opening."""
        return {
            "damper": self._zone.get("value"),
            "my_zone": self._zone.get("number") == self._ac.get("myZone"),
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Open or close the zone."""
        await self.async_set_zone(
            {"state": STATE_OPEN if hvac_mode != HVACMode.OFF else STATE_CLOSE}
        )

    async def async_turn_on(self) -> None:
        """Open the zone."""
        await self.async_set_zone({"state": STATE_OPEN})

    async def async_turn_off(self) -> None:
        """Close the zone."""
        await self.async_set_zone({"state": STATE_CLOSE})

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the zone's set point."""
        changes: dict[str, Any] = {}
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            changes["state"] = STATE_CLOSE if hvac_mode == HVACMode.OFF else STATE_OPEN
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            changes["setTemp"] = round(temp)
        if changes:
            await self.async_set_zone(changes)
