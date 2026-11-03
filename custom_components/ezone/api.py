"""Async client for the Advantage Air e-zone local API (v14/v15 firmware, port 2025).

Protocol notes (verified against a v15.1552 tablet):
* ``GET /getSystemData`` returns the whole system as JSON served as text/plain.
  Immediately after a write it can briefly answer ``{}``; callers must retry.
* Writes are ``GET /setAircon?json=<url-encoded JSON>`` (likewise ``setLights``
  / ``setThings``) and reply ``{"ack": true, ...}`` or
  ``{"ack": false, "reason": "..."}``.
* An empty payload makes the tablet drop the connection, so never send one.
* Unknown paths answer 200 with the version banner (``Advantage Air v15.1552``),
  which is also how old port-80 firmware can be told apart.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)
READ_ATTEMPTS = 4
WRITE_ATTEMPTS = 3
RETRY_DELAY = 0.5


class EzoneError(Exception):
    """Base error for the e-zone client."""


class EzoneConnectionError(EzoneError):
    """The tablet could not be reached or did not answer properly."""


class EzoneUnsupportedError(EzoneError):
    """The tablet answered but does not speak the port-2025 JSON API."""


class EzoneCommandError(EzoneError):
    """The tablet rejected a command (``ack: false``)."""


def deep_merge(target: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``changes`` into ``target`` (in place) and return it."""
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)
        else:
            target[key] = value
    return target


class EzoneClient:
    """Talk to one e-zone / MyAir / MyPlace touch-screen tablet."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int = 2025,
    ) -> None:
        """Initialise the client."""
        self._session = session
        self.host = host
        self.port = port
        self._write_lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        """Return the tablet's base URL."""
        return f"http://{self.host}:{self.port}"

    async def _get_text(self, path: str, params: dict[str, str] | None = None) -> str:
        """Perform one GET and return the body as text."""
        try:
            async with self._session.get(
                f"{self.base_url}/{path}", params=params, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status != 200:
                    raise EzoneConnectionError(f"HTTP {resp.status} from /{path}")
                return await resp.text()
        except TimeoutError as err:
            raise EzoneConnectionError(f"Timed out talking to {self.base_url}") from err
        except aiohttp.ClientError as err:
            raise EzoneConnectionError(
                f"Error talking to {self.base_url}: {err}"
            ) from err

    async def async_get_banner(self) -> str:
        """Return the version banner, e.g. ``Advantage Air v15.1552``."""
        return (await self._get_text("")).strip()

    async def async_get_system_data(self) -> dict[str, Any]:
        """Return the full system document, retrying transient bad answers."""
        last_error: EzoneError | None = None
        for attempt in range(READ_ATTEMPTS):
            if attempt:
                await asyncio.sleep(RETRY_DELAY * attempt)
            try:
                text = await self._get_text("getSystemData")
            except EzoneConnectionError as err:
                last_error = err
                continue
            try:
                data = json.loads(text)
            except ValueError:
                if text.lstrip().startswith("Advantage Air"):
                    # Only the banner: legacy firmware without the JSON API.
                    raise EzoneUnsupportedError(
                        f"{text.strip()!r} does not support the JSON API"
                    ) from None
                last_error = EzoneConnectionError("Invalid JSON from getSystemData")
                continue
            if isinstance(data, dict) and "aircons" in data and "system" in data:
                return data
            # The tablet answers "{}" for a moment after a write.
            last_error = EzoneConnectionError("Incomplete system data from tablet")
        assert last_error is not None
        raise last_error

    async def _async_write(self, endpoint: str, payload: dict[str, Any]) -> None:
        """Send a write command and check the acknowledgement."""
        if not payload:
            raise ValueError("Refusing to send an empty payload")
        params = {"json": json.dumps(payload, separators=(",", ":"))}
        async with self._write_lock:
            last_error: EzoneError | None = None
            for attempt in range(WRITE_ATTEMPTS):
                if attempt:
                    await asyncio.sleep(RETRY_DELAY * attempt)
                try:
                    text = await self._get_text(endpoint, params)
                except EzoneConnectionError as err:
                    # Dropped connections are common on this tablet; the
                    # payloads are absolute values, so a resend is safe.
                    last_error = err
                    continue
                try:
                    reply = json.loads(text)
                except ValueError:
                    last_error = EzoneCommandError(
                        f"Unexpected reply to {endpoint}: {text.strip()[:100]}"
                    )
                    continue
                if not isinstance(reply, dict) or "ack" not in reply:
                    last_error = EzoneCommandError(
                        f"Unexpected reply to {endpoint}: {text.strip()[:100]}"
                    )
                    continue
                if reply["ack"] is True:
                    _LOGGER.debug("%s %s acknowledged", endpoint, params["json"])
                    return
                raise EzoneCommandError(reply.get("reason") or "Command rejected")
            assert last_error is not None
            raise last_error

    async def async_set_aircon(self, payload: dict[str, Any]) -> None:
        """Send ``{"ac1": {"info": {...}, "zones": {...}}}``-shaped changes."""
        await self._async_write("setAircon", payload)

    async def async_set_lights(self, payload: dict[str, Any]) -> None:
        """Send ``{"<light id>": {"id": ..., "state": ..., "value": ...}}``."""
        await self._async_write("setLights", payload)

    async def async_set_things(self, payload: dict[str, Any]) -> None:
        """Send ``{"<thing id>": {"id": ..., "value": ...}}``."""
        await self._async_write("setThings", payload)
