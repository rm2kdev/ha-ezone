"""Tests for cover, sensor, binary_sensor, switch, select, number, button and light."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.button import DOMAIN as BUTTON, SERVICE_PRESS
from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_POSITION,
    DOMAIN as COVER,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_SET_COVER_POSITION,
)
from homeassistant.components.light import ATTR_BRIGHTNESS, DOMAIN as LIGHT
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER,
    SERVICE_SET_VALUE,
)
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.switch import DOMAIN as SWITCH
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_CLOSED,
    STATE_OFF,
    STATE_ON,
    STATE_OPEN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .conftest import RID, FakeTablet


async def _call(hass: HomeAssistant, domain: str, service: str, entity: str, **data):
    await hass.services.async_call(
        domain, service, {ATTR_ENTITY_ID: entity, **data}, blocking=True
    )


# ---------------------------------------------------------------- dampers


async def test_zone_dampers(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Each percentage zone is a damper cover on its own device."""
    living = hass.states.get("cover.living_zone")
    assert living.state == STATE_OPEN
    assert living.attributes[ATTR_CURRENT_POSITION] == 100
    assert living.attributes["constant_zone"] is True
    assert living.attributes["device_class"] == "damper"
    server = hass.states.get("cover.server_zone")
    assert server.state == STATE_CLOSED
    assert server.attributes[ATTR_CURRENT_POSITION] == 0
    assert server.attributes["constant_zone"] is False

    await _call(hass, COVER, SERVICE_OPEN_COVER, "cover.server_zone")
    assert tablet.last_write[1] == {"ac1": {"zones": {"z04": {"state": "open"}}}}
    assert hass.states.get("cover.server_zone").attributes[ATTR_CURRENT_POSITION] == 100

    await _call(hass, COVER, SERVICE_CLOSE_COVER, "cover.server_zone")
    assert tablet.last_write[1] == {"ac1": {"zones": {"z04": {"state": "close"}}}}


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        (47, {"state": "open", "value": 45}),
        (48, {"state": "open", "value": 50}),
        (1, {"state": "open", "value": 5}),
        (100, {"state": "open", "value": 100}),
        (0, {"state": "close"}),
    ],
)
async def test_damper_position(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    tablet: FakeTablet,
    position: int,
    expected: dict,
) -> None:
    """Positions snap to the tablet's 5 % steps; 0 closes the zone."""
    await _call(
        hass,
        COVER,
        SERVICE_SET_COVER_POSITION,
        "cover.craft_zone",
        **{ATTR_POSITION: position},
    )
    assert tablet.last_write[1] == {"ac1": {"zones": {"z07": expected}}}


# ---------------------------------------------------------------- aircon extras


async def test_countdown_timers(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Countdown numbers write minutes, clamped to 12 h."""
    assert hass.states.get("number.ac_turn_off_in").state == "0"
    await _call(
        hass, NUMBER, SERVICE_SET_VALUE, "number.ac_turn_off_in", **{ATTR_VALUE: 90}
    )
    assert tablet.last_write[1] == {"ac1": {"info": {"countDownToOff": 90}}}
    assert hass.states.get("number.ac_turn_off_in").state == "90"
    await _call(
        hass, NUMBER, SERVICE_SET_VALUE, "number.ac_turn_on_in", **{ATTR_VALUE: 0}
    )
    assert tablet.last_write[1] == {"ac1": {"info": {"countDownToOn": 0}}}


async def test_feature_switches(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Quiet night mode and MyFan toggle their info flags."""
    assert hass.states.get("switch.ac_quiet_night_mode").state == STATE_OFF
    await _call(hass, SWITCH, SERVICE_TURN_ON, "switch.ac_quiet_night_mode")
    assert tablet.last_write[1] == {"ac1": {"info": {"quietNightModeEnabled": True}}}
    assert hass.states.get("switch.ac_quiet_night_mode").state == STATE_ON
    await _call(hass, SWITCH, SERVICE_TURN_OFF, "switch.ac_myfan")
    assert tablet.last_write[1] == {"ac1": {"info": {"aaAutoFanModeEnabled": False}}}
    # The real unit has no fresh-air damper ("none"), so no switch for it.
    assert hass.states.get("switch.ac_fresh_air") is None


async def test_diagnostic_entities(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Fault/filter/update sensors read the right fields."""
    assert hass.states.get("binary_sensor.ac_filter_needs_cleaning").state == STATE_OFF
    assert hass.states.get("binary_sensor.ac_fault").state == STATE_OFF
    assert hass.states.get("sensor.ac_error_code").state == "none"
    assert hass.states.get("binary_sensor.e_zone_tablet_app_update").state == STATE_OFF

    tablet.data["aircons"]["ac1"]["info"].update(
        {"filterCleanStatus": 1, "airconErrorCode": "E14"}
    )
    await init_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.ac_filter_needs_cleaning").state == STATE_ON
    assert hass.states.get("binary_sensor.ac_fault").state == STATE_ON
    assert hass.states.get("sensor.ac_error_code").state == "E14"
    assert hass.states.get("climate.ac").attributes["error_code"] == "E14"


async def test_disabled_by_default(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Noisy/rarely useful entities start disabled."""
    reg = er.async_get(hass)
    for entity_id in (
        "sensor.e_zone_outdoor_temperature",
        "binary_sensor.ac_quiet_night_mode_running",
    ):
        assert (
            reg.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
        )
    assert reg.async_get("climate.ac").unique_id == f"{RID}-ac1-climate"


# ---------------------------------------------------------------- scenes


async def test_scene_buttons(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Running a scene re-applies only its safe aircon fields."""
    state = hass.states.get("button.e_zone_run_morning_heat")
    assert state.attributes["schedule_enabled"] is True
    assert state.attributes["start_time"] == "06:15"
    assert state.attributes["aircon_stop_time"] == "10:15"
    assert state.attributes["active_days_mask"] == 127

    await _call(hass, BUTTON, SERVICE_PRESS, "button.e_zone_run_morning_heat")
    endpoint, payload = tablet.last_write
    assert endpoint == "setAircon"
    info = payload["ac1"]["info"]
    assert info == {
        "fan": "auto",
        "mode": "heat",
        "myZone": 0,
        "setTemp": 23.0,
        "state": "on",
    }
    assert "name" not in info and "uid" not in info and "freshAirStatus" not in info
    assert payload["ac1"]["zones"]["z04"] == {
        "setTemp": 24.0,
        "state": "close",
        "value": 100,
    }
    assert all(
        set(z) <= {"state", "value", "setTemp"}
        for z in payload["ac1"]["zones"].values()
    )
    assert hass.states.get("climate.ac").state == "heat"

    await _call(hass, BUTTON, SERVICE_PRESS, "button.e_zone_run_night_off")
    assert tablet.last_write[1] == {"ac1": {"info": {"state": "off"}}}
    assert hass.states.get("climate.ac").state == "off"


async def test_scene_with_nothing_to_apply(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """A scene whose aircon no longer exists raises instead of sending {}."""
    scene = tablet.data["myScenes"]["scenes"]["s10002"]
    scene["aircons"] = {"ac3": {"info": {"state": "off"}}}
    await init_integration.runtime_data.async_refresh()
    with pytest.raises(HomeAssistantError):
        await _call(hass, BUTTON, SERVICE_PRESS, "button.e_zone_run_night_off")
    assert tablet.writes == []


# ---------------------------------------------------------------- full system

FULL = pytest.mark.parametrize("fixture_name", ["system_data_full.json"])


@FULL
async def test_sensor_zone_entities(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Sensor zones get temperature, damper, motion and fault entities."""
    assert hass.states.get("sensor.bedroom_zone_temperature").state == "21.4"
    assert hass.states.get("sensor.bedroom_zone_damper").state == "100"
    assert hass.states.get("binary_sensor.bedroom_zone_motion").state == STATE_ON
    assert hass.states.get("binary_sensor.bedroom_zone_sensor_fault").state == STATE_OFF
    assert hass.states.get("cover.bedroom_zone") is None  # thermostat, not damper
    assert hass.states.get("sensor.upstairs_myauto_mode").state == "cool"


@FULL
async def test_myzone_select(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """MyZone lists sensor zones by name."""
    state = hass.states.get("select.ac_myzone")
    assert state.state == "Bedroom"
    assert state.attributes["options"] == ["none", "Bedroom"]
    await _call(
        hass, SELECT, SERVICE_SELECT_OPTION, "select.ac_myzone", **{ATTR_OPTION: "none"}
    )
    assert tablet.last_write[1] == {"ac1": {"info": {"myZone": 0}}}
    await _call(
        hass,
        SELECT,
        SERVICE_SELECT_OPTION,
        "select.ac_myzone",
        **{ATTR_OPTION: "Bedroom"},
    )
    assert tablet.last_write[1] == {"ac1": {"info": {"myZone": 3}}}


@FULL
async def test_fresh_air_switch(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Fresh air uses on/off strings."""
    await _call(hass, SWITCH, SERVICE_TURN_ON, "switch.ac_fresh_air")
    assert tablet.last_write[1] == {"ac1": {"info": {"freshAirStatus": "on"}}}


@FULL
async def test_mylights(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """MyLights dimmers and relays."""
    pendant = hass.states.get("light.e_zone_pendant")
    assert pendant.state == STATE_ON
    assert pendant.attributes[ATTR_BRIGHTNESS] == 128
    await _call(
        hass, LIGHT, SERVICE_TURN_ON, "light.e_zone_pendant", **{ATTR_BRIGHTNESS: 255}
    )
    assert tablet.last_write == (
        "setLights",
        {"l1": {"id": "l1", "state": "on", "value": 100}},
    )
    await _call(hass, LIGHT, SERVICE_TURN_OFF, "light.e_zone_pendant")
    assert tablet.last_write == ("setLights", {"l1": {"id": "l1", "state": "off"}})
    assert hass.states.get("light.e_zone_pendant").state == STATE_OFF

    porch = hass.states.get("light.e_zone_porch")
    assert porch.attributes["supported_color_modes"] == ["onoff"]
    await _call(
        hass, LIGHT, SERVICE_TURN_ON, "light.e_zone_porch", **{ATTR_BRIGHTNESS: 10}
    )
    assert tablet.last_write == ("setLights", {"l2": {"id": "l2", "state": "on"}})


@FULL
async def test_mythings(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """MyThings blinds, garage doors, relays and lights."""
    assert hass.states.get("cover.e_zone_blind").state == STATE_OPEN
    assert hass.states.get("cover.e_zone_garage").attributes["device_class"] == "garage"
    await _call(hass, COVER, SERVICE_CLOSE_COVER, "cover.e_zone_blind")
    assert tablet.last_write == ("setThings", {"t1": {"id": "t1", "value": 0}})
    await _call(hass, COVER, SERVICE_OPEN_COVER, "cover.e_zone_garage")
    assert tablet.last_write == ("setThings", {"t2": {"id": "t2", "value": 100}})

    assert hass.states.get("switch.e_zone_pump").state == STATE_ON
    await _call(hass, SWITCH, SERVICE_TURN_OFF, "switch.e_zone_pump")
    assert tablet.last_write == ("setThings", {"t3": {"id": "t3", "value": 0}})
    await _call(hass, SWITCH, SERVICE_TURN_ON, "switch.e_zone_pump")
    assert tablet.last_write == ("setThings", {"t3": {"id": "t3", "value": 100}})

    deck = hass.states.get("light.e_zone_deck_light")
    assert deck.attributes[ATTR_BRIGHTNESS] == 102
    await _call(
        hass, LIGHT, SERVICE_TURN_ON, "light.e_zone_deck_light", **{ATTR_BRIGHTNESS: 51}
    )
    assert tablet.last_write == ("setThings", {"t4": {"id": "t4", "value": 20}})
    await _call(hass, LIGHT, SERVICE_TURN_OFF, "light.e_zone_deck_light")
    assert tablet.last_write == ("setThings", {"t4": {"id": "t4", "value": 0}})


@FULL
async def test_outdoor_temperature(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Outdoor temperature is available when enabled and valid."""
    reg = er.async_get(hass)
    reg.async_update_entity("sensor.e_zone_outdoor_temperature", disabled_by=None)
    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.e_zone_outdoor_temperature").state == "8.8"
