# Prama Alert Bridge

## Scope

This project is exclusively for **Prama cameras**. The network also has 6 TP-Link VIGI cameras (at .201-.206) — those use ONVIF natively and are NOT part of this project.

## What This Is

A Home Assistant add-on that bridges the Prama camera's proprietary AI human/vehicle detection to Home Assistant via MQTT. Prama cameras have on-device AI that classifies motion targets as human or vehicle, but this is only exposed through a proprietary HTTP streaming API — not through standard ONVIF. This bridge fills that gap.

## Cameras

| Camera | Model | IP | MAC | Area | HA ONVIF Name | Status |
|--------|-------|----|-----|------|---------------|--------|
| Prama 6MP | PT-NC163D3-WNM(D2) | *(was 192.168.1.44, currently unknown)* | e4:28:a4:6b:88:55 | matt | six_mp_one | unavailable |
| Prama 4MP | PT-NC140D7-WNMS/AW(D2) | 192.168.1.35 | e4:28:a4:6e:e8:42 | *(not yet assigned)* | *(not yet added)* | new |

Both run firmware V5.8.5 (build 250729) and use the same pramaAPI protocol.

## Credentials

- **Web UI / pramaAPI (HTTP Digest Auth):** `admin` / `Py03.1949` — same for all cameras
- **ONVIF:** `xxx` / `py03.1949` — same for all cameras
- **MQTT broker (192.168.1.20):** `xxx` / `yyy`

## Architecture

```
Prama Camera                    This Add-on                    Home Assistant
┌─────────────┐     HTTPS      ┌──────────────────┐   MQTT    ┌─────────────┐
│ alertStream  │──────────────→│ prama_alert_bridge │────────→│ Mosquitto    │
│ (Digest Auth)│  multipart    │                    │          │ Broker       │
│              │  XML events   │ Parses XML,        │          │              │
│ On-device AI │               │ filters VMD+human, │  auto-   │ binary_sensor│
│ human/vehicle│               │ publishes ON       │discovery │ .motion_...  │
└─────────────┘               └──────────────────┘          └─────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `prama_alert_bridge.py` | Main bridge script — connects to alertStream, parses XML, publishes to MQTT |
| `config.yaml` | Camera + MQTT credentials (local dev) |
| `config.json` | HA add-on manifest (name, options schema, arch) |
| `Dockerfile` | Container build for HA add-on |
| `run.sh` | Entry point — reads HA add-on options, generates config, starts bridge |
| `requirements.txt` | Python deps: requests, paho-mqtt, pyyaml |
| `pramaproto.md` | Full reverse-engineered protocol documentation |

## How It Works

1. **Connects** to `https://<camera>/pramaAPI/Event/notification/alertStream` with HTTP Digest Auth
2. **Reads** multipart chunked HTTP response, splits on `--boundary`, extracts XML
3. **Filters** for `eventType=VMD` + `targetType=human` (or vehicle, configurable)
4. **Publishes** `ON` to MQTT state topic on each detection
5. **HA auto-discovery**: publishes retained config to `homeassistant/binary_sensor/prama_human/config` so HA auto-creates the entity
6. **off_delay**: HA automatically turns the sensor OFF after 120 seconds of no new ON messages

## MQTT Topics

| Topic | Payload | Retained | Purpose |
|-------|---------|----------|---------|
| `homeassistant/binary_sensor/prama_human/config` | JSON discovery | Yes | HA auto-creates binary_sensor |
| `prama/motion/human/state` | `ON` | No | Trigger sensor on detection |
| `prama/motion/human/attributes` | JSON | No | last_detection_time, target_type, channel |
| `prama/motion/human/availability` | `online`/`offline` | Yes | Bridge online status |

## HA Entity Created

`binary_sensor.motion_detected_with_occupancy_timeout_prama`

This matches the naming pattern of the existing 6 TP-Link cameras which use ONVIF:
- `binary_sensor.motion_detected_with_occupancy_timeout_front`
- `binary_sensor.motion_detected_with_occupancy_timeout_back`
- `binary_sensor.motion_detected_with_occupancy_timeout_left`
- etc.

## Camera API Protocol

See `pramaproto.md` for the complete reverse-engineered protocol reference.

**Critical facts:**
- API uses HTTP Digest Auth, HTTPS with self-signed cert
- XML namespace: `http://www.std-cgi.com/ver20/XMLSchema`
- Alert stream is multipart HTTP with `--boundary` separators
- Human detection is ONLY available via pramaAPI, NOT via ONVIF
- ONVIF must be explicitly enabled in camera web UI (disabled by default)
- Both PT-NC163D3 (6MP) and PT-NC140D7 (4MP) use identical pramaAPI
- Single add-on instance supports multiple cameras (v2.0.0+) via `cameras` array in config

## Development

### Running Locally
```bash
pip install -r requirements.txt
python3 prama_alert_bridge.py
```

### Testing MQTT
```bash
mosquitto_sub -h <ha_ip> -u <user> -P <pass> -t "prama/motion/#" -v
```

### Verifying in HA
Developer Tools → States → search for `binary_sensor.motion_detected_with_occupancy_timeout_prama`

## Dashboard Integration

The Prama camera is integrated into the "Mainest" dashboard (`dashboard-mainest`):

**Security view:**
- Conditional camera card (`camera.six_mp_one_mainstream`) — visible when motion detected
- Person detection tile (red, mdi:motion-sensor, 3x2 grid) — matches other cameras

**Home view:**
- Badge (accent color, mdi:motion-sensor, shows last_changed) — matches other cameras

All visibility is conditional on the binary_sensor being `on`.
