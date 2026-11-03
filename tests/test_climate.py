"""Tests for the climate platform."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ezone.api import EzoneCommandError, EzoneConnectionError
from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_PRESET_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    DOMAIN as CLIMATE,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import FakeTablet

AC = "climate.ac"


async def _call(hass: HomeAssistant, service: str, entity: str = AC, **data) -> None:
    await hass.services.async_call(
        CLIMATE, service, {ATTR_ENTITY_ID: entity, **data}, blocking=True
    )


async def test_state_from_real_unit(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """State matches the dump taken from the v15 unit."""
    state = hass.states.get(AC)
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_TEMPERATURE] == 23
    assert state.attributes[ATTR_FAN_MODE] == "auto"
    assert state.attributes[ATTR_HVAC_ACTION] == "off"
    assert state.attributes["current_temperature"] is None
    assert state.attributes[ATTR_HVAC_MODES] == [
        "off",
        "cool",
        "heat",
        "fan_only",
        "dry",
    ]
    assert ATTR_PRESET_MODE not in state.attributes
    assert state.attributes["min_temp"] == 16
    assert state.attributes["max_temp"] == 32


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (HVACMode.COOL, {"state": "on", "mode": "cool"}),
        (HVACMode.HEAT, {"state": "on", "mode": "heat"}),
        (HVACMode.FAN_ONLY, {"state": "on", "mode": "vent"}),
        (HVACMode.DRY, {"state": "on", "mode": "dry"}),
        (HVACMode.OFF, {"state": "off"}),
    ],
)
async def test_set_hvac_mode(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    tablet: FakeTablet,
    mode: HVACMode,
    expected: dict,
) -> None:
    """HVAC modes map to e-zone mode strings and power the unit on."""
    await _call(hass, SERVICE_SET_HVAC_MODE, **{ATTR_HVAC_MODE: mode})
    assert tablet.last_write == ("setAircon", {"ac1": {"info": expected}})
    assert hass.states.get(AC).state == mode


async def test_unsupported_hvac_mode(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """HEAT_COOL is refused on a unit without MyAuto."""
    with pytest.raises(HomeAssistantError):
        await _call(hass, SERVICE_SET_HVAC_MODE, **{ATTR_HVAC_MODE: HVACMode.HEAT_COOL})
    assert tablet.writes == []


async def test_turn_on_off(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Turn on resumes the last mode."""
    await _call(hass, SERVICE_TURN_ON)
    assert tablet.last_write[1] == {"ac1": {"info": {"state": "on"}}}
    assert hass.states.get(AC).state == HVACMode.HEAT
    await _call(hass, SERVICE_TURN_OFF)
    assert tablet.last_write[1] == {"ac1": {"info": {"state": "off"}}}


async def test_set_temperature(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Set points are whole degrees, optionally with a mode change."""
    await _call(hass, SERVICE_SET_TEMPERATURE, **{ATTR_TEMPERATURE: 24.6})
    assert tablet.last_write[1] == {"ac1": {"info": {"setTemp": 25}}}
    assert hass.states.get(AC).attributes[ATTR_TEMPERATURE] == 25

    await _call(
        hass,
        SERVICE_SET_TEMPERATURE,
        **{ATTR_TEMPERATURE: 21, ATTR_HVAC_MODE: HVACMode.COOL},
    )
    assert tablet.last_write[1] == {
        "ac1": {"info": {"state": "on", "mode": "cool", "setTemp": 21}}
    }


@pytest.mark.parametrize("fan", ["low", "medium", "high", "auto"])
async def test_set_fan_mode(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet, fan: str
) -> None:
    """Fan speeds pass straight through."""
    await _call(hass, SERVICE_SET_FAN_MODE, **{ATTR_FAN_MODE: fan})
    assert tablet.last_write[1] == {"ac1": {"info": {"fan": fan}}}


async def test_command_errors_raise(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Rejections and network errors surface as HomeAssistantError."""
    tablet.fail_writes = EzoneCommandError("Valid JSON, but nothing useful there.")
    with pytest.raises(HomeAssistantError, match="rejected"):
        await _call(hass, SERVICE_TURN_ON)
    tablet.fail_writes = EzoneConnectionError("timeout")
    with pytest.raises(HomeAssistantError, match="Could not send"):
        await _call(hass, SERVICE_TURN_ON)
    assert hass.states.get(AC).state == HVACMode.OFF


# --------------------------------------------------------------------------
# Feature-rich synthetic system: MyZone sensor on ac1, MyAuto + MyFan on ac2.


@pytest.mark.parametrize("fixture_name", ["system_data_full.json"])
async def test_myzone_sensor(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """With a MyZone sensor the zone's reading and set point drive the unit."""
    state = hass.states.get(AC)
    assert state.attributes["current_temperature"] == 21.4
    assert state.attributes[ATTR_TEMPERATURE] == 22
    assert state.attributes[ATTR_PRESET_MODE] == "myzone"
    assert set(state.attributes["preset_modes"]) == {"myzone", "mytemp", "myauto"}

    await _call(hass, SERVICE_SET_TEMPERATURE, **{ATTR_TEMPERATURE: 20})
    assert tablet.last_write[1] == {"ac1": {"zones": {"z03": {"setTemp": 20}}}}

    await _call(
        hass,
        SERVICE_SET_TEMPERATURE,
        **{ATTR_TEMPERATURE: 19, ATTR_HVAC_MODE: HVACMode.HEAT},
    )
    assert tablet.last_write[1] == {
        "ac1": {
            "zones": {"z03": {"setTemp": 19}},
            "info": {"state": "on", "mode": "heat"},
        }
    }


@pytest.mark.parametrize("fixture_name", ["system_data_full.json"])
async def test_presets(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Presets flip the MyTemp / MyAuto flags."""
    await _call(hass, SERVICE_SET_PRESET_MODE, **{ATTR_PRESET_MODE: "mytemp"})
    assert tablet.last_write[1] == {
        "ac1": {"info": {"climateControlModeEnabled": True, "myAutoModeEnabled": False}}
    }
    state = hass.states.get(AC)
    assert state.attributes[ATTR_PRESET_MODE] == "mytemp"
    # MyTemp hands temperature control to the zones.
    assert not (
        state.attributes["supported_features"] & ClimateEntityFeature.TARGET_TEMPERATURE
    )


@pytest.mark.parametrize("fixture_name", ["system_data_full.json"])
async def test_myauto_and_myfan(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """MyAuto exposes a range; auto fan maps to autoAA when MyFan is on."""
    state = hass.states.get("climate.upstairs")
    assert state.state == HVACMode.HEAT_COOL
    assert state.attributes[ATTR_HVAC_ACTION] == "cooling"
    assert state.attributes[ATTR_FAN_MODE] == "auto"
    assert state.attributes[ATTR_TARGET_TEMP_LOW] == 20
    assert state.attributes[ATTR_TARGET_TEMP_HIGH] == 25
    assert HVACMode.HEAT_COOL in state.attributes[ATTR_HVAC_MODES]

    await _call(
        hass,
        SERVICE_SET_TEMPERATURE,
        "climate.upstairs",
        **{ATTR_TARGET_TEMP_LOW: 19, ATTR_TARGET_TEMP_HIGH: 26},
    )
    assert tablet.last_write[1] == {
        "ac2": {"info": {"myAutoHeatTargetTemp": 19, "myAutoCoolTargetTemp": 26}}
    }
    await _call(
        hass, SERVICE_SET_FAN_MODE, "climate.upstairs", **{ATTR_FAN_MODE: "auto"}
    )
    assert tablet.last_write[1] == {"ac2": {"info": {"fan": "autoAA"}}}


@pytest.mark.parametrize("fixture_name", ["system_data_full.json"])
async def test_sensor_zone_climate(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Zones with sensors get their own thermostat."""
    zone = "climate.bedroom_zone"
    state = hass.states.get(zone)
    assert state.state == HVACMode.HEAT_COOL
    assert state.attributes["current_temperature"] == 21.4
    assert state.attributes[ATTR_TEMPERATURE] == 22
    assert state.attributes[ATTR_HVAC_ACTION] == "off"  # aircon is off

    await _call(hass, SERVICE_SET_TEMPERATURE, zone, **{ATTR_TEMPERATURE: 23})
    assert tablet.last_write[1] == {"ac1": {"zones": {"z03": {"setTemp": 23}}}}
    await _call(hass, SERVICE_SET_HVAC_MODE, zone, **{ATTR_HVAC_MODE: HVACMode.OFF})
    assert tablet.last_write[1] == {"ac1": {"zones": {"z03": {"state": "close"}}}}
    assert hass.states.get(zone).state == HVACMode.OFF
    await _call(hass, SERVICE_TURN_ON, zone)
    assert tablet.last_write[1] == {"ac1": {"zones": {"z03": {"state": "open"}}}}
    await _call(hass, SERVICE_TURN_OFF, zone)
    assert tablet.last_write[1] == {"ac1": {"zones": {"z03": {"state": "close"}}}}
