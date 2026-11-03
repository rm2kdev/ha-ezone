"""Entity base classes for the Advantage Air e-zone integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import EzoneCoordinator


def system_id(coordinator: EzoneCoordinator) -> str:
    """Return a stable identifier for the tablet."""
    return coordinator.config_entry.unique_id or coordinator.config_entry.entry_id


def hub_device_info(coordinator: EzoneCoordinator) -> DeviceInfo:
    """Device for the wall tablet itself."""
    system = coordinator.data["system"]
    return DeviceInfo(
        identifiers={(DOMAIN, system_id(coordinator))},
        manufacturer=MANUFACTURER,
        model=system.get("sysType") or "e-zone",
        model_id=system.get("tspModel"),
        name=system.get("name") or "e-zone",
        sw_version=system.get("myAppRev"),
        configuration_url=coordinator.client.base_url,
    )


def ac_device_info(coordinator: EzoneCoordinator, ac_key: str) -> DeviceInfo:
    """Device for one aircon (``ac1`` ... ``ac4``)."""
    sys_id = system_id(coordinator)
    info = coordinator.data["aircons"][ac_key]["info"]
    fw = None
    if "cbFWRevMajor" in info:
        fw = f"{info['cbFWRevMajor']}.{info.get('cbFWRevMinor', 0):02d}"
    return DeviceInfo(
        identifiers={(DOMAIN, f"{sys_id}-{ac_key}")},
        via_device=(DOMAIN, sys_id),
        manufacturer=MANUFACTURER,
        model="Ducted aircon",
        model_id=str(info["unitType"]) if "unitType" in info else None,
        name=info.get("name") or ac_key.upper(),
        sw_version=fw,
    )


def zone_device_info(
    coordinator: EzoneCoordinator, ac_key: str, zone_key: str
) -> DeviceInfo:
    """Device for one zone, so zones can be placed in their own areas."""
    sys_id = system_id(coordinator)
    zone = coordinator.data["aircons"][ac_key]["zones"][zone_key]
    return DeviceInfo(
        identifiers={(DOMAIN, f"{sys_id}-{ac_key}-{zone_key}")},
        via_device=(DOMAIN, f"{sys_id}-{ac_key}"),
        manufacturer=MANUFACTURER,
        model="Sensor zone" if zone.get("type", 0) > 0 else "Damper zone",
        name=f"{zone.get('name') or zone_key} zone",
    )


class EzoneEntity(CoordinatorEntity[EzoneCoordinator]):
    """Base entity attached to the touch-screen tablet device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EzoneCoordinator, key: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{system_id(coordinator)}-{key}"
        self._attr_device_info = hub_device_info(coordinator)

    @property
    def _system(self) -> dict[str, Any]:
        return self.coordinator.data["system"]


class EzoneAcEntity(CoordinatorEntity[EzoneCoordinator]):
    """Entity belonging to one aircon."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EzoneCoordinator, ac_key: str, key: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self.ac_key = ac_key
        self._attr_unique_id = f"{system_id(coordinator)}-{ac_key}-{key}"
        self._attr_device_info = ac_device_info(coordinator, ac_key)

    @property
    def available(self) -> bool:
        """Return if the aircon is still reported by the tablet."""
        return super().available and self.ac_key in self.coordinator.data.get(
            "aircons", {}
        )

    @property
    def _ac(self) -> dict[str, Any]:
        """Return this aircon's ``info`` block."""
        return self.coordinator.data["aircons"][self.ac_key]["info"]

    @property
    def _zones(self) -> dict[str, dict[str, Any]]:
        return self.coordinator.data["aircons"][self.ac_key].get("zones", {})

    @property
    def _myzone(self) -> dict[str, Any] | None:
        """Return the zone currently acting as the temperature reference."""
        if number := self._ac.get("myZone"):
            return self._zones.get(f"z{int(number):02d}")
        return None

    async def async_set_ac(self, changes: dict[str, Any]) -> None:
        """Write to this aircon's ``info`` block."""
        await self.coordinator.async_set_ac_info(self.ac_key, changes)


class EzoneZoneEntity(EzoneAcEntity):
    """Entity belonging to one zone; each zone is its own device."""

    def __init__(
        self, coordinator: EzoneCoordinator, ac_key: str, zone_key: str, key: str
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator, ac_key, f"{zone_key}-{key}")
        self.zone_key = zone_key
        self._attr_device_info = zone_device_info(coordinator, ac_key, zone_key)

    @property
    def available(self) -> bool:
        """Return if the zone is still reported by the tablet."""
        return super().available and self.zone_key in self._zones

    @property
    def _zone(self) -> dict[str, Any]:
        return self._zones[self.zone_key]

    @property
    def _is_constant(self) -> bool:
        """Return True if this zone is a constant (always-open) zone."""
        number = self._zone.get("number")
        return any(
            self._ac.get(f"constant{i}") == number
            for i in range(1, int(self._ac.get("noOfConstants", 0)) + 1)
        )

    async def async_set_zone(self, changes: dict[str, Any]) -> None:
        """Write to this zone."""
        await self.coordinator.async_set_zone(self.ac_key, self.zone_key, changes)
