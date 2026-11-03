"""Binary sensor platform for the Advantage Air e-zone integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EzoneConfigEntry, EzoneCoordinator
from .entity import EzoneAcEntity, EzoneEntity, EzoneZoneEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EzoneAcBinaryDescription(BinarySensorEntityDescription):
    """Describes an aircon-level binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool]
    exists_fn: Callable[[dict[str, Any]], bool] = lambda info: True


AC_BINARY_SENSORS: tuple[EzoneAcBinaryDescription, ...] = (
    EzoneAcBinaryDescription(
        key="filter",
        translation_key="filter",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda info: bool(info.get("filterCleanStatus")),
        exists_fn=lambda info: "filterCleanStatus" in info,
    ),
    EzoneAcBinaryDescription(
        key="fault",
        translation_key="fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda info: bool(info.get("airconErrorCode")),
        exists_fn=lambda info: "airconErrorCode" in info,
    ),
    EzoneAcBinaryDescription(
        key="quiet_night_running",
        translation_key="quiet_night_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda info: bool(info.get("quietNightModeIsRunning")),
        exists_fn=lambda info: "quietNightModeIsRunning" in info,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EzoneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [EzoneUpdateAvailable(coordinator)]
    for ac_key, ac in coordinator.data.get("aircons", {}).items():
        entities.extend(
            EzoneAcBinarySensor(coordinator, ac_key, desc)
            for desc in AC_BINARY_SENSORS
            if desc.exists_fn(ac["info"])
        )
        for zone_key, zone in ac.get("zones", {}).items():
            if zone.get("motionConfig", 0) >= 2:
                entities.append(EzoneZoneMotion(coordinator, ac_key, zone_key))
            if zone.get("type", 0) > 0:
                entities.append(EzoneZoneSensorFault(coordinator, ac_key, zone_key))
    async_add_entities(entities)


class EzoneAcBinarySensor(EzoneAcEntity, BinarySensorEntity):
    """Generic aircon binary sensor."""

    entity_description: EzoneAcBinaryDescription

    def __init__(
        self,
        coordinator: EzoneCoordinator,
        ac_key: str,
        description: EzoneAcBinaryDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, ac_key, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.entity_description.value_fn(self._ac)


class EzoneUpdateAvailable(EzoneEntity, BinarySensorEntity):
    """The tablet app reports that an update is available."""

    _attr_translation_key = "app_update"
    _attr_device_class = BinarySensorDeviceClass.UPDATE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EzoneCoordinator) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, "app_update")

    @property
    def is_on(self) -> bool:
        """Return True if the tablet wants an update."""
        return bool(self._system.get("needsUpdate"))


class EzoneZoneMotion(EzoneZoneEntity, BinarySensorEntity):
    """Zone motion sensor (when motion detection is enabled for the zone)."""

    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(
        self, coordinator: EzoneCoordinator, ac_key: str, zone_key: str
    ) -> None:
        """Initialise the motion sensor."""
        super().__init__(coordinator, ac_key, zone_key, "motion")

    @property
    def is_on(self) -> bool:
        """Return True when motion is detected (the tablet reports 20)."""
        return self._zone.get("motion") == 20


class EzoneZoneSensorFault(EzoneZoneEntity, BinarySensorEntity):
    """Problem with a zone's wireless temperature sensor."""

    _attr_translation_key = "sensor_fault"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: EzoneCoordinator, ac_key: str, zone_key: str
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, ac_key, zone_key, "sensor_fault")

    @property
    def is_on(self) -> bool:
        """Return True on a sensor error or a duplicate-sensor clash."""
        return bool(self._zone.get("error")) or bool(self._zone.get("tempSensorClash"))
