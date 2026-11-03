"""Tests for setup, unload, polling, devices and diagnostics."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.ezone.api import EzoneConnectionError, EzoneUnsupportedError
from custom_components.ezone.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .conftest import RID, FakeTablet


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The entry loads and unloads cleanly."""
    assert init_integration.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def test_setup_retry_when_unreachable(
    hass: HomeAssistant, config_entry: MockConfigEntry, tablet: FakeTablet
) -> None:
    """An unreachable tablet puts the entry in setup-retry."""
    tablet.fail_reads = EzoneConnectionError("No route to host")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_retry_unsupported(
    hass: HomeAssistant, config_entry: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Old firmware is reported, not crashed on."""
    tablet.fail_reads = EzoneUnsupportedError("banner only")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_polling_and_unavailable(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    tablet: FakeTablet,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Changes made on the tablet show up; outages mark entities unavailable."""
    assert hass.states.get("climate.ac").state == "off"
    tablet.data["aircons"]["ac1"]["info"].update({"state": "on", "mode": "cool"})
    freezer.tick(timedelta(seconds=16))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("climate.ac").state == "cool"

    tablet.fail_reads = EzoneConnectionError("gone")
    freezer.tick(timedelta(seconds=16))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("climate.ac").state == STATE_UNAVAILABLE
    assert hass.states.get("cover.living_zone").state == STATE_UNAVAILABLE

    tablet.fail_reads = None
    freezer.tick(timedelta(seconds=16))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("climate.ac").state == "cool"


async def test_device_tree(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Tablet -> aircon -> zone devices are linked."""
    reg = dr.async_get(hass)
    hub = reg.async_get_device(identifiers={(DOMAIN, RID)})
    ac = reg.async_get_device(identifiers={(DOMAIN, f"{RID}-ac1")})
    zone = reg.async_get_device(identifiers={(DOMAIN, f"{RID}-ac1-z04")})
    assert hub.name == "e-zone"
    assert hub.model == "e-zone"
    assert hub.model_id == "PIC7GS8"
    assert hub.sw_version == "15.1552"
    assert ac.name == "AC"
    assert ac.via_device_id == hub.id
    assert ac.sw_version == "8.46"
    assert zone.name == "Server zone"
    assert zone.via_device_id == ac.id
    devices = dr.async_entries_for_config_entry(reg, init_integration.entry_id)
    assert len(devices) == 1 + 1 + 7


async def test_diagnostics_redacts_secrets(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    tablet: FakeTablet,
) -> None:
    """Location, PINs and phone push tokens never leave in diagnostics."""
    tablet.data["system"].update(
        {
            "latitude": -31.9,
            "longitude": 115.8,
            "logoPIN": "1234",
            "deviceIds": ["secret-token"],
            "postCode": "6069",
        }
    )
    await init_integration.runtime_data.async_refresh()
    diag = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)
    text = str(diag)
    for secret in (
        "-31.9",
        "115.8",
        "1234",
        "secret-token",
        "6069",
        RID,
        "192.168.1.26",
    ):
        assert secret not in text, secret
    assert diag["data"]["aircons"]["ac1"]["info"]["name"] == "AC"
