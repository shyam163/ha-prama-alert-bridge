# Prama Camera — Home Assistant Integration

[![Home Assistant](https://img.shields.io/badge/HA-Integration-blue?logo=homeassistant)](https://www.home-assistant.io/)

Native Home Assistant integration for **Prama camera AI human/vehicle detection**.

Prama IP cameras have on-device AI that classifies motion as human or vehicle, but this detection is only available through a proprietary API (`pramaAPI`) — not through ONVIF or any standard protocol. This integration connects to the camera's real-time alert stream and creates a `binary_sensor` entity directly in HA — no MQTT broker needed.

## Evolution

This project started as an MQTT-based HA add-on (v1.0–v2.0) and was rewritten as a native custom integration for better UX:

| Version | Architecture | Config | Dependencies |
|---------|-------------|--------|--------------|
| v1.0 (add-on) | Docker container → MQTT → HA | Manual YAML | Mosquitto broker |
| v2.0 (add-on) | Multi-camera threading → MQTT → HA | HA add-on UI | Mosquitto broker |
| **v1.0 (integration)** | **Native HA component, daemon thread** | **Config flow with validation** | **None** |

The native integration is simpler, faster, and validates camera credentials before saving.

## Install

### Via HACS (recommended)

1. Open HACS in Home Assistant
2. Click **Integrations** → **Custom repositories**
3. Add `https://github.com/shyam163/ha-prama-alert-bridge` as an **Integration**
4. Search for "Prama Camera" and install
5. Restart Home Assistant

### Manual

1. Copy `custom_components/prama/` to your HA `config/custom_components/prama/`
2. Restart Home Assistant

## Setup

1. Go to **Settings → Devices & Integrations → Add Integration**
2. Search for **"Prama Camera"**
3. Enter camera IP, credentials, sensor name, and off-delay
4. The integration validates the connection before saving
5. Add the integration again for each additional camera

## How It Works

```
Prama Camera                     HA Integration (custom_components/prama/)
+--------------+     HTTPS       +-----------------------------------+
| alertStream  |---------------->| AlertStreamManager (daemon thread) |
| (Digest Auth)|  multipart XML  |                                   |
|              |                 | PramaMotionBinarySensor            |
| On-device AI |                 |   binary_sensor.prama_<name>_motion|
| human/vehicle|                 +-----------------------------------+
+--------------+                     |
                                     | call_soon_threadsafe
                                     v
                                  HA Event Loop
                                  (state updates, auto-off timer)
```

1. **Config flow** validates credentials by calling `/pramaAPI/System/deviceInfo`
2. **AlertStreamManager** runs in a daemon thread, connecting to the camera's `alertStream`
3. Parses multipart XML events, filters for `eventType=VMD` + `targetType=human|vehicle`
4. Posts detections to HA's event loop via `call_soon_threadsafe`
5. **PramaMotionBinarySensor** turns ON, schedules auto-OFF via `async_call_later`
6. Auto-reconnects with exponential backoff (5s → 60s) on connection loss

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| Camera Host | *(required)* | Camera IP address (e.g., 192.168.1.35) |
| Username | `admin` | Camera web UI username |
| Password | *(required)* | Camera web UI password |
| Sensor Name | `prama` | Used in entity ID (e.g., `prama_4mp`) |
| Off Delay | `120` | Seconds before sensor turns OFF (10-600) |

## Entity Created

`binary_sensor.prama_<sensor_name>_motion`

**Attributes:** `last_detection_time`, `target_type`, `channel`, `event_state`

## Multi-Camera

Add the integration once per camera. Each camera gets its own config entry, entity, and independent alert stream connection.

## Supported Cameras

Tested on:
- **Prama PT-NC163D3-WNM(D2)** — 6MP, firmware V5.8.5
- **Prama PT-NC140D7-WNMS/AW(D2)** — 4MP, firmware V5.8.5

Both use the identical `pramaAPI` protocol. Should work with other Prama cameras that expose the `alertStream` endpoint.

## Protocol Documentation

See [pramaproto.md](pramaproto.md) for the complete reverse-engineered Prama API reference.

## License

MIT
