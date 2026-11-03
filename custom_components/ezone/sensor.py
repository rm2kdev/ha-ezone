"""Sensor platform for the Advantage Air e-zone integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import INFO_MYAUTO_CURRENT_MODE, INFO_MYAUTO_ENABLED, STATE_OPEN
from .coordinator import EzoneConfigEntry, EzoneCoordinator
from .entity import EzoneAcEntity, EzoneEntity, EzoneZoneEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EzoneAcSensorDescription(SensorEntityDescription):
    """Describes an aircon-level sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    exists_fn: Callable[[dict[str, Any]], bool] = lambda info: True


AC_SENSORS: tuple[EzoneAcSensorDescription, ...] = (
    EzoneAcSensorDescription(
        key="error_code",
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda info: info.get("airconErrorCode") or "none",
    ),
    EzoneAcSensorDescription(
        key="myauto_mode",
        translation_key="myauto_mode",
        device_class=SensorDeviceClass.ENUM,
        options=["cool", "heat", "vent", "dry"],
        value_fn=lambda info: (
            info.get(INFO_MYAUTO_CURRENT_MODE) if info.get("mode") == "myauto" else None
        ),
        exists_fn=lambda info: INFO_MYAUTO_ENABLED in info,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EzoneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [EzoneOutdoorTemp(coordinator)]
    for ac_key, ac in coordinator.data.get("aircons", {}).items():
        entities.extend(
            EzoneAcSensor(coordinator, ac_key, desc)
            for desc in AC_SENSORS
            if desc.exists_fn(ac["info"])
        )
        for zone_key, zone in ac.get("zones", {}).items():
            if zone.get("type", 0) > 0:
                entities.append(EzoneZoneTemperature(coordinator, ac_key, zone_key))
                entities.append(EzoneZoneDamperSensor(coordinator, ac_key, zone_key))
            if zone.get("rssi", 0) > 0:
                entities.append(EzoneZoneSignal(coordinator, ac_key, zone_key))
    async_add_entities(entities)


class EzoneAcSensor(EzoneAcEntity, SensorEntity):
    """Generic aircon sensor."""

    entity_description: EzoneAcSensorDescription

    def __init__(
        self,
        coordinator: EzoneCoordinator,
        ac_key: str,
        description: EzoneAcSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, ac_key, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the value."""
        return self.entity_description.value_fn(self._ac)


class EzoneOutdoorTemp(EzoneEntity, SensorEntity):
    """Outdoor (suburb) temperature the tablet fetches from the cloud."""

    _attr_translation_key = "outdoor_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: EzoneCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "outdoor_temperature")

    @property
    def available(self) -> bool:
        """Only available while the tablet reports a valid reading."""
        return super().available and bool(self._system.get("isValidSuburbTemp"))

    @property
    def native_value(self) -> float | None:
        """Return the outdoor temperature."""
        return self._system.get("suburbTemp")


class EzoneZoneTemperature(EzoneZoneEntity, SensorEntity):
    """Zone sensor temperature."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(
        self, coordinator: EzoneCoordinator, ac_key: str, zone_key: str
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, ac_key, zone_key, "temperature")

    @property
    def native_value(self) -> float | None:
        """Return the measured temperature."""
        return self._zone.get("measuredTemp")


class EzoneZoneDamperSensor(EzoneZoneEntity, SensorEntity):
    """Damper opening of a temperature-controlled zone (set by the tablet)."""

    _attr_translation_key = "damper"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: EzoneCoordinator, ac_key: str, zone_key: str
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, ac_key, zone_key, "damper_sensor")

    @property
    def native_value(self) -> int:
        """Return the damper opening."""
        if self._zone.get("state") == STATE_OPEN:
            return int(self._zone.get("value", 0))
        return 0


class EzoneZoneSignal(EzoneZoneEntity, SensorEntity):
    """Wireless sensor signal strength."""

    _attr_translation_key = "signal"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator: EzoneCoordinator, ac_key: str, zone_key: str
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, ac_key, zone_key, "signal")

    @property
    def native_value(self) -> int:
        """Return the RSSI value reported by the tablet (0-100)."""
        return int(self._zone.get("rssi", 0))
