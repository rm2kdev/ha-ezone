"""Build the AC dashboard config (built-in cards only) and print it as JSON."""

from __future__ import annotations

import json

ZONES = [
    ("cover.living_zone", "Living", "mdi:sofa"),
    ("cover.lounge_zone", "Lounge", "mdi:television"),
    ("cover.bedroom_zone", "Bedroom", "mdi:bed-king"),
    ("cover.lins_office_zone", "Lin's Office", "mdi:desk"),
    ("cover.ryan_office_zone", "Ryan's Office", "mdi:monitor"),
    ("cover.craft_zone", "Craft", "mdi:palette"),
    ("cover.server_zone", "Server", "mdi:server"),
]
ZONE_IDS = [z[0] for z in ZONES]


def action_button(name: str, icon: str, service: str, target: list[str] | str) -> dict:
    return {
        "type": "button",
        "name": name,
        "icon": icon,
        "show_state": False,
        "icon_height": "32px",
        "tap_action": {
            "action": "perform-action",
            "perform_action": service,
            "target": {"entity_id": target},
        },
        "grid_options": {"columns": 6, "rows": 2},
    }


def zone_tile(entity: str, name: str, icon: str) -> dict:
    return {
        "type": "tile",
        "entity": entity,
        "name": name,
        "icon": icon,
        "vertical": False,
        "state_content": ["state", "current_position"],
        # Tap toggles the zone; hold opens the damper % slider. The tile's
        # cover-position bar draws covers shade-style (fill = closed), which
        # reads backwards for dampers, so it's left off the tile.
        "tap_action": {"action": "toggle"},
        "hold_action": {"action": "more-info"},
        "grid_options": {"columns": 6, "rows": 1},
    }


def scene_tile(entity: str, name: str, icon: str) -> dict:
    return {
        "type": "tile",
        "entity": entity,
        "name": name,
        "icon": icon,
        "hide_state": True,
        "tap_action": {
            "action": "perform-action",
            "perform_action": "button.press",
            "target": {"entity_id": entity},
            "confirmation": {"text": f"Run scene '{name}'?"},
        },
        "grid_options": {"columns": 6, "rows": 1},
    }


aircon_section = {
    "type": "grid",
    "cards": [
        {
            "type": "heading",
            "heading": "Aircon",
            "icon": "mdi:air-conditioner",
            "badges": [
                {
                    "type": "entity",
                    "entity": "binary_sensor.ac_filter_needs_cleaning",
                    "show_state": True,
                    "show_icon": True,
                    "color": "red",
                    "visibility": [
                        {
                            "condition": "state",
                            "entity": "binary_sensor.ac_filter_needs_cleaning",
                            "state": "on",
                        }
                    ],
                },
                {
                    "type": "entity",
                    "entity": "sensor.ac_error_code",
                    "show_state": True,
                    "show_icon": True,
                    "color": "red",
                    "visibility": [
                        {
                            "condition": "state",
                            "entity": "sensor.ac_error_code",
                            "state_not": "none",
                        }
                    ],
                },
            ],
        },
        {
            "type": "thermostat",
            "entity": "climate.ac",
            "name": "AC",
            "show_current_as_primary": False,
            "features": [
                {
                    "type": "climate-hvac-modes",
                    "style": "icons",
                    "hvac_modes": ["off", "cool", "heat", "fan_only", "dry"],
                },
                {
                    "type": "climate-fan-modes",
                    "style": "icons",
                    "fan_modes": ["low", "medium", "high", "auto"],
                },
            ],
        },
        scene_tile(
            "button.e_zone_run_morning_heat", "Morning heat", "mdi:weather-sunset-up"
        ),
        scene_tile("button.e_zone_run_night_off", "Night off", "mdi:weather-night"),
    ],
}

zones_section = {
    "type": "grid",
    "cards": [
        {"type": "heading", "heading": "Zones", "icon": "mdi:floor-plan"},
        action_button("All zones on", "mdi:hvac", "cover.open_cover", ZONE_IDS),
        action_button("All zones off", "mdi:hvac-off", "cover.close_cover", ZONE_IDS),
        *[zone_tile(*z) for z in ZONES],
    ],
}

timers_section = {
    "type": "grid",
    "cards": [
        {
            "type": "heading",
            "heading": "Timers & settings",
            "icon": "mdi:timer-outline",
        },
        {
            "type": "tile",
            "entity": "number.ac_turn_on_in",
            "name": "Turn on in",
            "icon": "mdi:timer-play-outline",
            "features": [{"type": "numeric-input", "style": "buttons"}],
            "grid_options": {"columns": 12, "rows": 2},
        },
        {
            "type": "tile",
            "entity": "number.ac_turn_off_in",
            "name": "Turn off in",
            "icon": "mdi:timer-stop-outline",
            "features": [{"type": "numeric-input", "style": "buttons"}],
            "grid_options": {"columns": 12, "rows": 2},
        },
        action_button(
            "Off in 30 min",
            "mdi:timer-sand",
            "number.set_value",
            "number.ac_turn_off_in",
        )
        | {
            "tap_action": {
                "action": "perform-action",
                "perform_action": "number.set_value",
                "target": {"entity_id": "number.ac_turn_off_in"},
                "data": {"value": 30},
            }
        },
        action_button(
            "Off in 2 h",
            "mdi:timer-sand-complete",
            "number.set_value",
            "number.ac_turn_off_in",
        )
        | {
            "tap_action": {
                "action": "perform-action",
                "perform_action": "number.set_value",
                "target": {"entity_id": "number.ac_turn_off_in"},
                "data": {"value": 120},
            }
        },
        {
            "type": "tile",
            "entity": "switch.ac_quiet_night_mode",
            "name": "Quiet night mode",
            "tap_action": {"action": "toggle"},
            "grid_options": {"columns": 6, "rows": 1},
        },
        {
            "type": "tile",
            "entity": "switch.ac_myfan",
            "name": "MyFan",
            "tap_action": {"action": "toggle"},
            "grid_options": {"columns": 6, "rows": 1},
        },
        {
            "type": "tile",
            "entity": "binary_sensor.ac_filter_needs_cleaning",
            "name": "Filter",
            "grid_options": {"columns": 6, "rows": 1},
        },
        {
            "type": "tile",
            "entity": "binary_sensor.ac_fault",
            "name": "Fault",
            "grid_options": {"columns": 6, "rows": 1},
        },
    ],
}

config = {
    "title": "Air Conditioning",
    "views": [
        {
            "title": "AC",
            "path": "ac",
            "icon": "mdi:air-conditioner",
            "type": "sections",
            "max_columns": 3,
            "sections": [aircon_section, zones_section, timers_section],
        }
    ],
}

if __name__ == "__main__":
    print(json.dumps(config))
