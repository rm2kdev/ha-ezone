# Advantage Air e-zone for Home Assistant

A local-polling Home Assistant integration for Advantage Air **e-zone**, **MyAir** and **MyPlace** ducted air-conditioning systems running tablet firmware v14 or later. It talks to the wall tablet's JSON API on port 2025. There's no cloud and no account.

It's built from the protocol notes in [this gist](https://gist.github.com/rm2kdev/c0cde5c007951b2955465b2db491e30c) and checked against a tablet running `Advantage Air v15.1552`.

## Install

### HACS (custom repository)

1. In HACS, open the menu, choose **Custom repositories**, add `https://github.com/rm2kdev/ha-ezone` and pick the **Integration** category.
2. Install **Advantage Air e-zone**, then restart Home Assistant.

### Manual

Copy `custom_components/ezone` into `<config>/custom_components/`, then restart Home Assistant.

## Set up

Go to **Settings → Devices & services → Add integration → Advantage Air e-zone** and enter the tablet's IP address. Leave the port at 2025.

Give the tablet a DHCP reservation. If its address changes anyway, use **Reconfigure** on the integration to point it at the new one. You can't accidentally point the entry at a different tablet, because the tablet's cloud id is checked.

Under **Configure** you can change the poll interval (default 15 s, range 5–300 s). After you change something from Home Assistant, the integration re-reads the tablet about a second later, whatever the poll interval is.

## What you get

Devices are created as a tree: **tablet → aircon → one device per zone**. You can put each zone device in its own area.

| Entity | Notes |
| --- | --- |
| `climate.<aircon>` | Off / Cool / Heat / Fan only / Dry (plus Heat-Cool on MyAuto units). Fan low/medium/high/auto. Set point in whole °C, 16–32. Presets MyZone / MyTemp / MyAuto appear only when the unit supports them. When a MyZone sensor is selected, its reading and set point drive the thermostat. |
| `cover.<zone>_zone` | One per percentage (damper) zone, device class `damper`. Open/close turns the zone on/off. Position sets the damper in 5 % steps, and 0 closes the zone. Attributes show the zone number and whether it's a constant zone. |
| `climate.<zone>_zone` | One per zone with a wireless temperature sensor (replaces the cover): zone on/off and the zone set point. |
| `sensor.<zone>_zone_temperature` / `_damper` / `_sensor_signal` | For sensor zones. Signal is disabled by default. |
| `binary_sensor.<zone>_zone_motion` / `_sensor_fault` | Motion (when enabled on the zone) and a sensor fault or duplicate-sensor clash. |
| `number.<aircon>_turn_on_in` / `_turn_off_in` | Countdown timers in minutes (0 cancels, 720 max). |
| `switch.<aircon>_quiet_night_mode`, `_myfan`, `_fresh_air` | Created only when the unit reports the feature. Fresh air needs a fresh-air damper fitted. |
| `select.<aircon>_myzone` | Which sensor zone the aircon follows. Only on systems with sensor zones. |
| `binary_sensor.<aircon>_filter_needs_cleaning`, `_fault`; `sensor.<aircon>_error_code` | Diagnostics. |
| `button.<tablet>_run_<scene>` | One per MyScene saved on the tablet. Pressing it applies the scene's aircon settings. Attributes show the scene's schedule as configured on the tablet. |
| `sensor.<tablet>_outdoor_temperature` | The suburb temperature the tablet downloads. Disabled by default, and unavailable while the tablet reports it as invalid. |
| `binary_sensor.<tablet>_tablet_app_update` | The tablet says an app update is available. |
| MyLights lights, MyThings blinds / garage doors / relays / lights | Set up automatically when the tablet has them. |

### How scenes are run

The tablet's own `/runScene` payload isn't documented. Pressing a scene button instead sends the aircon state stored in the scene through `/setAircon`. Only power, mode, fan, set points, MyZone and zone open/close/damper/set-point fields are sent. The aircon and zone names and ids stored in the scene are never written back.

## Protocol notes and quirks

* `GET /getSystemData` returns everything. Right after a write it can briefly answer `{}`, so the client retries reads (4 attempts with back-off) and only accepts a document that contains `aircons` and `system`.
* Writes are `GET /set{Aircon,Lights,Things}?json=<url-encoded JSON>` and reply `{"ack":true}` or `{"ack":false,"reason":"..."}`. A rejection becomes a Home Assistant error with the tablet's reason. A dropped connection is retried, which is safe because every payload sets absolute values.
* The tablet drops the connection if it's sent an empty payload, so the client refuses to send one.
* Set points are whole degrees. The tablet acks `23.5` but keeps `23`.
* Old port-80 firmware only answers with a version banner. The config flow reports it as unsupported firmware.

## Diagnostics and privacy

The tablet's `system` block includes the install's latitude and longitude, postcode, logo PIN, paired phone names and push tokens. Anyone on your LAN can read these from the tablet. **Download diagnostics** redacts them, along with the tablet IP and cloud ids.

## Development

```bash
uv venv --python 3.14 .venv
uv pip install homeassistant==2026.4.1 pytest-homeassistant-custom-component==0.13.322 ruff
scripts/test.sh            # ruff + pytest with coverage
```

`scripts/dev_ha.py` drives a throwaway local Home Assistant (`dev-config/`, port 8129) for end-to-end checks against a real tablet. Run `scripts/gen_translations.py` after editing `strings.json`.

> **macOS note:** Local Network privacy can block LAN access for some Python builds (`[Errno 65] No route to host`) even when `curl` works. Build the venv from an interpreter that has Local Network permission.

## Relationship to the core `advantage_air` integration

Home Assistant ships an `advantage_air` integration for the same API. This integration uses its own domain (`ezone`), so the two can be installed side by side, but don't run both against one tablet. Remove the core entry once you've moved over.
