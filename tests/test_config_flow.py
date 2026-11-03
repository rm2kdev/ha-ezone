"""Tests for the e-zone config, reconfigure and options flows."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ezone.api import (
    EzoneConnectionError,
    EzoneUnsupportedError,
)
from custom_components.ezone.const import CONF_SCAN_INTERVAL, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import HOST, RID, FakeTablet


async def test_user_flow(hass: HomeAssistant, tablet: FakeTablet) -> None:
    """Happy path creates an entry keyed by the tablet's rid."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: f" {HOST} ", CONF_PORT: 2025}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "e-zone"
    assert result["data"] == {CONF_HOST: HOST, CONF_PORT: 2025}
    assert result["result"].unique_id == RID


async def test_user_flow_errors_then_recovers(
    hass: HomeAssistant, tablet: FakeTablet
) -> None:
    """Connection problems show errors and the form can be retried."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    tablet.fail_reads = EzoneConnectionError("nope")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: 2025}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    tablet.fail_reads = EzoneUnsupportedError("legacy")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: 80}
    )
    assert result["errors"] == {"base": "unsupported_firmware"}

    tablet.fail_reads = RuntimeError("surprise")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: 2025}
    )
    assert result["errors"] == {"base": "unknown"}

    tablet.fail_reads = None
    tablet.data["aircons"] = {}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: 2025}
    )
    assert result["errors"] == {"base": "no_aircons"}


async def test_user_flow_already_configured(
    hass: HomeAssistant, tablet: FakeTablet, config_entry: MockConfigEntry
) -> None:
    """The same tablet can't be added twice; a new IP updates the entry."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.99", CONF_PORT: 2025}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == "192.168.1.99"


async def test_unique_id_falls_back_to_address(
    hass: HomeAssistant, tablet: FakeTablet
) -> None:
    """Tablets without a cloud rid are keyed by host:port."""
    tablet.data["system"].pop("rid")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: 2025}
    )
    assert result["result"].unique_id == f"{HOST}:2025"


async def test_reconfigure(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Reconfigure moves the entry to a new address."""
    result = await init_integration.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    tablet.fail_reads = EzoneConnectionError("nope")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.5", CONF_PORT: 2025}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    tablet.fail_reads = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.5", CONF_PORT: 2025}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert init_integration.data[CONF_HOST] == "10.0.0.5"


async def test_reconfigure_wrong_device(
    hass: HomeAssistant, init_integration: MockConfigEntry, tablet: FakeTablet
) -> None:
    """Pointing the entry at a different tablet is refused."""
    result = await init_integration.start_reconfigure_flow(hass)
    tablet.data["system"]["rid"] = "SOMEOTHERTABLET"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.6", CONF_PORT: 2025}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert init_integration.data[CONF_HOST] == HOST


async def test_options_flow(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The poll interval can be changed and triggers a reload."""
    coordinator = init_integration.runtime_data
    assert coordinator.update_interval.total_seconds() == 15

    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 30}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == {CONF_SCAN_INTERVAL: 30}
    assert init_integration.runtime_data.update_interval.total_seconds() == 30
