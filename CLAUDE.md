# Prama Camera Integration

## Scope

This project is exclusively for **Prama cameras**. The network also has 6 TP-Link VIGI cameras (at .201-.206) — those use ONVIF natively and are NOT part of this project.

## What This Is

A Home Assistant custom integration that bridges Prama camera proprietary AI human/vehicle detection to HA. Prama cameras have on-device AI that classifies motion targets as human or vehicle, but this is only exposed through a proprietary HTTP streaming API — not through standard ONVIF. This integration fills that gap.

### Evolution

Started as an MQTT-based HA add-on (v1.0–v2.0), rewritten as a native custom integration for:
- Config flow with credential validation (no more YAML editing)
- No MQTT dependency (direct entity creation)
- Cleaner architecture (daemon thread + call_soon_threadsafe)
- Key lesson: never import `requests`/`urllib3` at module top level in HA integrations — causes 500 errors on Python 3.14. Use lazy imports inside blocking functions.

## Cameras

| Camera | Model | IP | MAC | Area | HA Entity | Status |
|--------|-------|----|-----|------|-----------|--------|
| Prama 6MP | PT-NC163D3-WNM(D2) | *(unknown — old IP .44 is now dev machine)* | e4:28:a4:6b:88:55 | matt | — | unavailable |
| Prama 4MP | PT-NC140D7-WNMS/AW(D2) | 192.168.1.35 | e4:28:a4:6e:e8:42 | — | `binary_sensor.prama_prama_4mp_motion` | working |

Both run firmware V5.8.5 (build 250729) and use the same pramaAPI protocol.

## Credentials

- **Web UI / pramaAPI (HTTP Digest Auth):** `admin` / `Py03.1949` — same for all cameras
- **ONVIF:** `xxx` / `py03.1949` — same for all cameras
- **MQTT broker (192.168.1.20):** `xxx` / `yyy`

## Architecture

```
Prama Camera                     custom_components/prama/
┌─────────────┐     HTTPS        ┌──────────────────────────────────┐
│ alertStream  │────────────────→│ AlertStreamManager               │
│ (Digest Auth)│  multipart XML  │   (daemon thread per camera)     │
│              │                 │                                   │
│ On-device AI │                 │ PramaMotionBinarySensor           │
│ human/vehicle│                 │   auto-off via async_call_later   │
└─────────────┘                 └──────────────────────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `custom_components/prama/__init__.py` | Integration setup, startup validation, entry load/unload |
| `custom_components/prama/config_flow.py` | Config flow with pramaAPI credential validation |
| `custom_components/prama/binary_sensor.py` | Motion detection entity with auto-off timer |
| `custom_components/prama/alert_stream.py` | AlertStreamManager — daemon thread, reconnect loop, XML parsing |
| `custom_components/prama/const.py` | Constants (domain, config keys, API endpoints) |
| `custom_components/prama/manifest.json` | Integration metadata |
| `custom_components/prama/strings.json` | Config flow UI strings |
| `pramaproto.md` | Full reverse-engineered protocol documentation |

## How It Works

1. **Config flow** validates credentials by calling `https://<host>/pramaAPI/System/deviceInfo` with Digest Auth
2. **On setup**, creates `PramaMotionBinarySensor` and starts `AlertStreamManager` in a daemon thread
3. **AlertStreamManager** connects to `alertStream`, reads multipart XML chunks, splits on `--boundary`
4. **Filters** for `eventType=VMD` + `targetType=human` (default)
5. **Posts** detections to HA event loop via `hass.loop.call_soon_threadsafe(callback, alert)`
6. **Sensor** turns ON, schedules auto-OFF after `off_delay` seconds via `async_call_later`
7. **Auto-reconnects** with exponential backoff (5s → 60s) on connection loss

## Camera API Protocol

See `pramaproto.md` for the complete reverse-engineered protocol reference.

**Critical facts:**
- API uses HTTP Digest Auth, HTTPS with self-signed cert
- XML namespace: `http://www.std-cgi.com/ver20/XMLSchema`
- Alert stream is multipart HTTP with `--boundary` separators
- Human detection is ONLY available via pramaAPI, NOT via ONVIF
- ONVIF must be explicitly enabled in camera web UI (disabled by default)
- Both PT-NC163D3 (6MP) and PT-NC140D7 (4MP) use identical pramaAPI

## Development

### Deploying to HA
```bash
# Upload via Samba
smbclient //192.168.1.20/config -U "xxx%yyy" -c "cd custom_components\\prama; put <file>"
# ALWAYS clear bytecode cache after upload
smbclient //192.168.1.20/config -U "xxx%yyy" -c "cd custom_components\\prama\\__pycache__; del <file>.cpython-314.pyc"
```

### Critical: Lazy Imports
Never import `requests`, `urllib3`, or other blocking libraries at module top level. Always import inside the blocking function that runs via `async_add_executor_job`. Top-level `urllib3.disable_warnings()` causes 500 errors on HA with Python 3.14.

### Verifying in HA
Developer Tools → States → search for `binary_sensor.prama_`

## Dashboard Integration

The Prama camera is integrated into the "Mainest" dashboard (`dashboard-mainest`):

**Security view:**
- Conditional camera card — visible when motion detected
- Person detection tile (red, mdi:motion-sensor, 3x2 grid) — matches other cameras

**Home view:**
- Badge (accent color, mdi:motion-sensor, shows last_changed) — matches other cameras

All visibility is conditional on the binary_sensor being `on`.
