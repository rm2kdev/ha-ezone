"""Fixtures for the e-zone integration tests."""

from __future__ import annotations

from collections.abc import Generator
import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ezone.api import EzoneConnectionError, deep_merge
from custom_components.ezone.const import DOMAIN
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

FIXTURES = Path(__file__).parent / "fixtures"
HOST = "192.168.1.26"
RID = "TESTRID0000000000000000000"


def load_fixture_data(name: str) -> dict[str, Any]:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom_components in every test."""


class FakeTablet:
    """In-memory stand-in for EzoneClient that behaves like the real tablet."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.host = HOST
        self.port = 2025
        self.writes: list[tuple[str, dict[str, Any]]] = []
        self.fail_reads: Exception | None = None
        self.fail_writes: Exception | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def __call__(self, session: Any, host: str, port: int = 2025) -> FakeTablet:
        """Act as the EzoneClient constructor."""
        self.host, self.port = host, port
        return self

    async def async_get_system_data(self) -> dict[str, Any]:
        if self.fail_reads:
            raise self.fail_reads
        return copy.deepcopy(self.data)

    async def _write(self, endpoint: str, payload: dict[str, Any]) -> None:
        if self.fail_writes:
            raise self.fail_writes
        self.writes.append((endpoint, copy.deepcopy(payload)))

    async def async_set_aircon(self, payload: dict[str, Any]) -> None:
        await self._write("setAircon", payload)
        deep_merge(self.data["aircons"], payload)

    async def async_set_lights(self, payload: dict[str, Any]) -> None:
        await self._write("setLights", payload)
        deep_merge(self.data["myLights"]["lights"], payload)

    async def async_set_things(self, payload: dict[str, Any]) -> None:
        await self._write("setThings", payload)
        deep_merge(self.data["myThings"]["things"], payload)

    @property
    def last_write(self) -> tuple[str, dict[str, Any]]:
        return self.writes[-1]


@pytest.fixture
def fixture_name() -> str:
    """Which system dump to serve (override per module/test)."""
    return "system_data.json"


@pytest.fixture
def tablet(fixture_name: str) -> Generator[FakeTablet]:
    """Patch EzoneClient everywhere with a FakeTablet."""
    fake = FakeTablet(load_fixture_data(fixture_name))
    with (
        patch("custom_components.ezone.EzoneClient", fake),
        patch("custom_components.ezone.config_flow.EzoneClient", fake),
    ):
        yield fake


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry for the test tablet."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="e-zone",
        data={CONF_HOST: HOST, CONF_PORT: 2025},
        unique_id=RID,
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry, tablet: FakeTablet
) -> MockConfigEntry:
    """Set up the integration against the fake tablet."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


__all__ = ["EzoneConnectionError"]
