"""Drive a local dev Home Assistant (scripts/dev-config) over REST.

python scripts/dev_ha.py onboard            # create dev user, store token
python scripts/dev_ha.py add <host> [port]  # run the ezone config flow
python scripts/dev_ha.py states [prefix]    # list ezone entity states
python scripts/dev_ha.py call <domain> <service> '<json data>'
python scripts/dev_ha.py get <path>
"""

from __future__ import annotations

import json
from pathlib import Path
import secrets
import sys
from typing import Any
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8129"
TOKEN_FILE = Path(__file__).resolve().parent.parent / "dev-config" / ".dev_token"
CLIENT_ID = f"{BASE}/"


def _req(method: str, path: str, data: object | None = None, form: bool = False) -> Any:
    headers = {}
    body = None
    if TOKEN_FILE.exists():
        headers["Authorization"] = f"Bearer {TOKEN_FILE.read_text().strip()}"
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode()
    try:
        return json.loads(text)
    except ValueError:
        return text


def onboard() -> None:
    res = _req(
        "POST",
        "/api/onboarding/users",
        {
            "client_id": CLIENT_ID,
            "name": "Dev",
            "username": "dev",
            "password": secrets.token_urlsafe(16),
            "language": "en",
        },
    )
    tok = _req(
        "POST",
        "/auth/token",
        {
            "grant_type": "authorization_code",
            "code": res["auth_code"],
            "client_id": CLIENT_ID,
        },
        form=True,
    )
    TOKEN_FILE.write_text(tok["access_token"])
    print("token stored", TOKEN_FILE)


def add(host: str, port: int) -> None:
    flow = _req("POST", "/api/config/config_entries/flow", {"handler": "ezone"})
    print(json.dumps(flow, indent=1))
    res = _req(
        "POST",
        f"/api/config/config_entries/flow/{flow['flow_id']}",
        {"host": host, "port": port},
    )
    print(json.dumps(res, indent=1))


def states(prefix: str = "") -> None:
    ents = _req("GET", "/api/states")
    reg = {e["entity_id"] for e in ents}
    for s in sorted(ents, key=lambda e: e["entity_id"]):
        if prefix and not s["entity_id"].startswith(prefix):
            continue
        print(
            s["entity_id"],
            "=",
            s["state"],
            json.dumps(s["attributes"], default=str)[:300],
        )
    print(len(reg), "entities")


def main() -> None:
    cmd, *args = sys.argv[1:]
    if cmd == "onboard":
        onboard()
    elif cmd == "add":
        add(args[0], int(args[1]) if len(args) > 1 else 2025)
    elif cmd == "states":
        states(*args)
    elif cmd == "call":
        domain, service, data = args[0], args[1], json.loads(args[2])
        print(_req("POST", f"/api/services/{domain}/{service}", data))
    elif cmd == "get":
        print(json.dumps(_req("GET", args[0]), indent=1))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
