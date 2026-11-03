"""Tests for the e-zone HTTP client against mocked tablet responses."""

from __future__ import annotations

import json
from unittest.mock import patch

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.ezone.api import (
    EzoneClient,
    EzoneCommandError,
    EzoneConnectionError,
    EzoneUnsupportedError,
    deep_merge,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import load_fixture_data

BASE = "http://192.168.1.26:2025"


@pytest.fixture(autouse=True)
def no_sleep():
    """Skip retry back-off delays."""
    with patch("custom_components.ezone.api.asyncio.sleep"):
        yield


def _client(hass: HomeAssistant) -> EzoneClient:
    return EzoneClient(async_get_clientsession(hass), "192.168.1.26", 2025)


async def test_get_system_data(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A good document is returned as-is (served as text/plain)."""
    data = load_fixture_data("system_data.json")
    aioclient_mock.get(f"{BASE}/getSystemData", text=json.dumps(data))
    assert await _client(hass).async_get_system_data() == data


async def test_get_system_data_retries_empty(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The tablet briefly answers {} after a write; the client retries."""
    data = load_fixture_data("system_data.json")
    replies = iter(["{}", "{}", json.dumps(data)])

    async def side_effect(method, url, body):
        from pytest_homeassistant_custom_component.test_util.aiohttp import (
            AiohttpClientMockResponse,
        )

        return AiohttpClientMockResponse(method, url, text=next(replies))

    aioclient_mock.get(f"{BASE}/getSystemData", side_effect=side_effect)
    assert await _client(hass).async_get_system_data() == data
    assert aioclient_mock.call_count == 3


async def test_get_system_data_gives_up(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Persistent junk raises a connection error."""
    aioclient_mock.get(f"{BASE}/getSystemData", text="{}")
    with pytest.raises(EzoneConnectionError):
        await _client(hass).async_get_system_data()
    assert aioclient_mock.call_count == 4


async def test_get_system_data_legacy_banner(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Only the version banner means the JSON API is missing."""
    aioclient_mock.get(f"{BASE}/getSystemData", text="Advantage Air v10.2")
    with pytest.raises(EzoneUnsupportedError):
        await _client(hass).async_get_system_data()


@pytest.mark.parametrize("exc", [aiohttp.ClientConnectionError("boom"), TimeoutError()])
async def test_get_system_data_connection_errors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, exc: Exception
) -> None:
    """Network failures surface as EzoneConnectionError."""
    aioclient_mock.get(f"{BASE}/getSystemData", exc=exc)
    with pytest.raises(EzoneConnectionError):
        await _client(hass).async_get_system_data()


async def test_http_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Non-200 answers are errors."""
    aioclient_mock.get(f"{BASE}/getSystemData", status=500)
    with pytest.raises(EzoneConnectionError):
        await _client(hass).async_get_system_data()


async def test_banner(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """The root path returns the version banner."""
    aioclient_mock.get(f"{BASE}/", text="Advantage Air v15.1552\n")
    assert await _client(hass).async_get_banner() == "Advantage Air v15.1552"


async def test_set_aircon_encodes_payload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Writes send compact JSON in the json query parameter."""
    aioclient_mock.get(f"{BASE}/setAircon", text='{"ack":true,"request":"setAircon"}')
    payload = {"ac1": {"info": {"state": "on", "setTemp": 23}}}
    await _client(hass).async_set_aircon(payload)
    _, url, _, _ = aioclient_mock.mock_calls[0]
    assert json.loads(url.query["json"]) == payload
    assert url.query["json"] == '{"ac1":{"info":{"state":"on","setTemp":23}}}'


async def test_set_aircon_rejected(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """ack:false raises with the tablet's reason."""
    aioclient_mock.get(
        f"{BASE}/setAircon",
        text='{"ack":false,"reason":"Valid JSON, but nothing useful there.","request":"setAircon"}',
    )
    with pytest.raises(EzoneCommandError, match="nothing useful"):
        await _client(hass).async_set_aircon({"ac1": {"info": {"mode": "bogus"}}})
    assert aioclient_mock.call_count == 1  # rejections are not retried


async def test_set_aircon_retries_dropped_connection(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A dropped connection is retried, then reported."""
    aioclient_mock.get(f"{BASE}/setAircon", exc=aiohttp.ServerDisconnectedError())
    with pytest.raises(EzoneConnectionError):
        await _client(hass).async_set_aircon({"ac1": {"info": {"setTemp": 23}}})
    assert aioclient_mock.call_count == 3


async def test_set_aircon_unexpected_reply(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A banner or other junk instead of an ack is an error."""
    aioclient_mock.get(f"{BASE}/setAircon", text="Advantage Air v15.1552")
    with pytest.raises(EzoneCommandError):
        await _client(hass).async_set_aircon({"ac1": {"info": {"setTemp": 23}}})


async def test_empty_payload_refused(hass: HomeAssistant) -> None:
    """An empty payload would make the tablet drop the connection."""
    with pytest.raises(ValueError):
        await _client(hass).async_set_aircon({})


async def test_lights_and_things_endpoints(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Lights and things use their own endpoints."""
    aioclient_mock.get(f"{BASE}/setLights", text='{"ack":true}')
    aioclient_mock.get(f"{BASE}/setThings", text='{"ack":true}')
    client = _client(hass)
    await client.async_set_lights({"l1": {"id": "l1", "state": "on"}})
    await client.async_set_things({"t1": {"id": "t1", "value": 100}})
    assert [c[1].path for c in aioclient_mock.mock_calls] == [
        "/setLights",
        "/setThings",
    ]


def test_deep_merge() -> None:
    """Nested dicts merge; scalars overwrite."""
    target = {"a": {"b": 1, "c": {"d": 2}}, "e": 3}
    deep_merge(target, {"a": {"c": {"d": 5, "f": 6}}, "e": {"x": 1}})
    assert target == {"a": {"b": 1, "c": {"d": 5, "f": 6}}, "e": {"x": 1}}
