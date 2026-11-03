"""Tiny Home Assistant websocket client for dev/deploy chores.

Usage: python scripts/ha_ws.py '<json message without id>' [...more messages]
Reads HASS_URL / HASS_TOKEN from the environment.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import aiohttp


async def main(messages: list[dict]) -> None:
    url = os.environ["HASS_URL"].rstrip("/").replace("http", "ws", 1) + "/api/websocket"
    token = os.environ["HASS_TOKEN"]
    async with (
        aiohttp.ClientSession() as session,
        session.ws_connect(url, max_msg_size=0) as ws,
    ):
        await ws.receive_json()  # auth_required
        await ws.send_json({"type": "auth", "access_token": token})
        auth = await ws.receive_json()
        if auth.get("type") != "auth_ok":
            raise SystemExit(f"auth failed: {auth}")
        for i, msg in enumerate(messages, start=1):
            await ws.send_json({"id": i, **msg})
            while True:
                reply = await asyncio.wait_for(ws.receive_json(), timeout=120)
                if reply.get("id") == i and reply.get("type") == "result":
                    print(json.dumps(reply, indent=1, default=str))
                    break


if __name__ == "__main__":
    asyncio.run(main([json.loads(a) for a in sys.argv[1:]]))
