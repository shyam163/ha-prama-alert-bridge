# Prama Alert Bridge — Home Assistant Add-on

[![Home Assistant Add-on](https://img.shields.io/badge/HA-Add--on-blue?logo=homeassistant)](https://www.home-assistant.io/addons/)

Bridges **Prama camera AI human/vehicle detection** to Home Assistant via MQTT auto-discovery.

Prama IP cameras have powerful on-device AI that classifies motion as human or vehicle, but this detection is only available through a proprietary API (`pramaAPI`) — not through ONVIF or any standard protocol. This add-on connects to the camera's real-time alert stream, parses the events, and publishes them to MQTT so Home Assistant can use them natively.

## Quick Install

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**
2. Click the **⋮** menu (top right) → **Repositories**
3. Add this repository URL:
   ```
   https://github.com/shyam-prama/ha-prama-alert-bridge
   ```
4. Find **Prama Alert Bridge** in the store and click **Install**
5. Configure your camera IP, credentials, and MQTT broker details
6. Start the add-on

## What It Does

- Connects to the Prama camera's `alertStream` endpoint (HTTPS, Digest Auth)
- Parses multipart XML events in real-time
- Filters for AI-classified human and/or vehicle detection
- Publishes to MQTT with HA auto-discovery
- Creates a `binary_sensor.motion_detected_with_occupancy_timeout_<name>` entity
- Sensor auto-turns OFF after configurable timeout (default: 2 minutes)
- Auto-reconnects on connection loss with exponential backoff

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `camera_host` | *(required)* | Camera IP address |
| `camera_username` | `admin` | Camera login username |
| `camera_password` | *(required)* | Camera login password |
| `mqtt_host` | *(required)* | MQTT broker IP (usually your HA IP) |
| `mqtt_port` | `1883` | MQTT broker port |
| `mqtt_username` | *(required)* | MQTT username |
| `mqtt_password` | *(required)* | MQTT password |
| `detection_types` | `[human]` | AI types to detect: `human`, `vehicle` |
| `off_delay` | `120` | Seconds before sensor turns OFF (10-600) |
| `sensor_name` | `prama` | Name used in entity ID and MQTT topics |
| `log_level` | `info` | Logging: `debug`, `info`, `warning`, `error` |

## Prerequisites

- Prama IP camera with AI detection (tested: PT-NC163D3-WNM(D2))
- Mosquitto MQTT broker add-on running in Home Assistant
- MQTT integration configured in Home Assistant

## Entity Created

`binary_sensor.motion_detected_with_occupancy_timeout_<sensor_name>`

This follows the same naming pattern as ONVIF camera motion sensors, so it integrates seamlessly with existing dashboard cards and automations.

**Attributes:** `last_detection_time`, `target_type`, `channel`, `event_state`

## Supported Cameras

Tested on:
- **Prama PT-NC163D3-WNM(D2)** (firmware V5.8.5, build 250729)

Should work with other Prama cameras using the `pramaAPI` protocol. If you test on a different model, please open an issue with your results.

## Protocol Documentation

See [pramaproto.md](pramaproto.md) for the complete reverse-engineered Prama API reference, including:
- All API endpoints (System, Streaming, Events, Security)
- Alert stream format and XML parsing details
- Motion detection configuration
- ONVIF limitations

## License

MIT
