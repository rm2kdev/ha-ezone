"""Generate translations/en.json from strings.json.

Custom integrations can't use core's ``[%key:common::...%]`` references at
runtime, so resolve them here. Run after editing strings.json.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "ezone"

COMMON = {
    "common::config_flow::data::host": "Host",
    "common::config_flow::data::port": "Port",
    "common::config_flow::error::cannot_connect": "Failed to connect",
    "common::config_flow::error::unknown": "Unexpected error",
    "common::config_flow::abort::already_configured_device": "Device is already configured",
    "common::config_flow::abort::reconfigure_successful": "Re-configuration was successful",
}


def resolve(value: object) -> object:
    if isinstance(value, dict):
        return {k: resolve(v) for k, v in value.items()}
    if isinstance(value, str):
        return re.sub(r"\[%key:([^%]+)%\]", lambda m: COMMON[m.group(1)], value)
    return value


def main() -> None:
    strings = json.loads((ROOT / "strings.json").read_text())
    out = ROOT / "translations" / "en.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(resolve(strings), indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
