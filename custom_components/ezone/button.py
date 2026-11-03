"""Button platform: run a MyScene from the tablet.

The tablet's own ``/runScene`` payload is undocumented, so a scene is run by
re-applying the aircon state it stores through ``/setAircon``. Only fields that
are safe to write (power, mode, fan, set points, zones) are sent; names and ids
in the stored snapshot are ignored.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, SCENE_INFO_FIELDS, SCENE_ZONE_FIELDS
from .coordinator import EzoneConfigEntry, EzoneCoordinator
from .entity import EzoneEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EzoneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one button per stored scene."""
    coordinator = entry.runtime_data
    scenes = coordinator.data.get("myScenes", {}).get("scenes", {})
    async_add_entities(
        EzoneSceneButton(coordinator, scene_id)
        for scene_id, scene in scenes.items()
        if scene.get("aircons")
    )


def scene_payload(scene: dict[str, Any], aircons: dict[str, Any]) -> dict[str, Any]:
    """Build a sanitised ``setAircon`` payload from a stored scene."""
    payload: dict[str, Any] = {}
    for ac_key, ac in (scene.get("aircons") or {}).items():
        if ac_key not in aircons:
            continue
        body: dict[str, Any] = {}
        info = {
            k: v for k, v in (ac.get("info") or {}).items() if k in SCENE_INFO_FIELDS
        }
        if info.get("freshAirStatus") == "none":
            info.pop("freshAirStatus")
        if info:
            body["info"] = info
        known_zones = aircons[ac_key].get("zones", {})
        zones = {}
        for zone_key, zone in (ac.get("zones") or {}).items():
            if zone_key not in known_zones:
                continue
            fields = {k: v for k, v in zone.items() if k in SCENE_ZONE_FIELDS}
            if fields:
                zones[zone_key] = fields
        if zones:
            body["zones"] = zones
        if body:
            payload[ac_key] = body
    return payload


def _fmt_minutes(minutes: Any) -> str | None:
    if not isinstance(minutes, int):
        return None
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class EzoneSceneButton(EzoneEntity, ButtonEntity):
    """Apply a stored MyScene's aircon settings."""

    _attr_translation_key = "scene"

    def __init__(self, coordinator: EzoneCoordinator, scene_id: str) -> None:
        """Initialise the button."""
        super().__init__(coordinator, f"scene-{scene_id}")
        self._id = scene_id
        self._attr_translation_placeholders = {
            "name": self._scene.get("name") or scene_id
        }

    @property
    def available(self) -> bool:
        """Return if the scene still exists on the tablet."""
        return super().available and self._id in self.coordinator.data.get(
            "myScenes", {}
        ).get("scenes", {})

    @property
    def _scene(self) -> dict[str, Any]:
        return self.coordinator.data["myScenes"]["scenes"][self._id]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the scene's schedule as configured on the tablet."""
        scene = self._scene
        attrs: dict[str, Any] = {
            "scene_id": self._id,
            "schedule_enabled": bool(scene.get("timerEnabled")),
            "start_time": _fmt_minutes(scene.get("startTime")),
            "active_days_mask": scene.get("activeDays"),
        }
        if scene.get("airconStopTimeEnabled"):
            attrs["aircon_stop_time"] = _fmt_minutes(scene.get("airconStopTime"))
        if summary := scene.get("summary"):
            attrs["summary"] = summary
        return attrs

    async def async_press(self) -> None:
        """Apply the scene."""
        payload = scene_payload(self._scene, self.coordinator.data.get("aircons", {}))
        if not payload:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="empty_scene",
                translation_placeholders={"name": self._scene.get("name", self._id)},
            )
        await self.coordinator.async_set_aircon(payload)
