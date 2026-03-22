# Prama Alert Bridge

## Overview

This add-on bridges the **Prama camera's AI-powered human and vehicle detection** to Home Assistant via MQTT. Prama cameras (e.g., PT-NC163D3-WNM(D2)) have on-device AI that classifies motion targets, but this data is only available through a proprietary HTTP API — not through standard protocols like ONVIF.

The add-on connects to the camera's alert stream, filters for the detection types you care about, and publishes events to MQTT with Home Assistant auto-discovery. This creates a `binary_sensor` entity that behaves identically to ONVIF motion sensors from other cameras.

## How It Works

```
Prama Camera                  This Add-on                Home Assistant
┌─────────────┐    HTTPS     ┌────────────────┐  MQTT   ┌─────────────┐
│ alertStream  │────────────→│ Alert Bridge    │────────→│ Mosquitto   │
│ (pramaAPI)   │  multipart  │ Parse XML       │         │ Broker      │
│              │  XML events │ Filter VMD      │  auto   │             │
│ On-device AI │             │ Publish ON      │ discov. │ binary_     │
│ human/vehicle│             │                 │────────→│ sensor.*    │
└─────────────┘             └────────────────┘         └─────────────┘
```

1. Connects to `https://<camera>/pramaAPI/Event/notification/alertStream` with HTTP Digest Auth
2. Reads the multipart chunked response, splits on `--boundary`, parses XML
3. Filters for `eventType=VMD` with matching `targetType` (human/vehicle)
4. Publishes `ON` to MQTT state topic on each detection
5. Home Assistant auto-creates the `binary_sensor` via MQTT discovery
6. The sensor auto-turns OFF after the configured timeout (off_delay)

## Prerequisites

- **Prama IP camera** with AI detection capability (tested on PT-NC163D3-WNM(D2))
- **Mosquitto MQTT broker** add-on installed and running in Home Assistant
- **MQTT integration** configured in Home Assistant
- Camera must be reachable from Home Assistant over the network

## Configuration

### Camera Host
The IP address of your Prama camera (e.g., `192.168.1.44`). The camera must be reachable via HTTPS on port 443.

### Camera Credentials
The admin username and password for your camera. These are the same credentials you use to log into the camera's web UI.

### MQTT Settings
Point to your MQTT broker. If you're using the Mosquitto add-on in HA, the host is your Home Assistant IP address (e.g., `192.168.1.20`), port 1883.

### Detection Types
Choose which AI detection types to bridge:
- **human** — triggers on people
- **vehicle** — triggers on cars, trucks, motorcycles

You can select both to trigger on any classified motion.

### Off Delay
The occupancy timeout in seconds (default: 120). The sensor stays ON as long as detections keep arriving. Once no detection is received for this many seconds, the sensor turns OFF.

This matches the `motion_detected_with_occupancy_timeout` pattern used by ONVIF cameras in Home Assistant.

### Sensor Name
A short identifier used in the entity ID and MQTT topics. Default: `prama`.

- Entity created: `binary_sensor.motion_detected_with_occupancy_timeout_<sensor_name>`
- MQTT topics: `prama/<sensor_name>/motion/state`

For multiple cameras, use distinct names like `prama_front`, `prama_back`.

## Multi-Camera Setup

To monitor multiple Prama cameras, install one instance of this add-on per camera. Each instance needs a unique `sensor_name` to avoid MQTT topic conflicts.

Alternatively, future versions may support multiple cameras in a single instance.

## Entity Created

The add-on auto-creates via MQTT discovery:

**Entity ID:** `binary_sensor.motion_detected_with_occupancy_timeout_<sensor_name>`

**Attributes:**
| Attribute | Description |
|-----------|-------------|
| `last_detection_time` | ISO 8601 timestamp of last detection |
| `target_type` | `human` or `vehicle` |
| `channel` | Camera channel ID |
| `event_state` | `active` or `inactive` |

## Dashboard Usage

### Conditional Camera Card
Show the camera feed only when motion is detected:

```yaml
type: picture-entity
entity: camera.your_prama_camera
camera_view: live
visibility:
  - condition: state
    entity: binary_sensor.motion_detected_with_occupancy_timeout_prama
    state: "on"
```

### Motion Badge
Show a badge in the header when motion is active:

```yaml
type: entity
entity: binary_sensor.motion_detected_with_occupancy_timeout_prama
name: Prama
icon: mdi:motion-sensor
color: accent
state_content: last_changed
visibility:
  - condition: state
    entity: binary_sensor.motion_detected_with_occupancy_timeout_prama
    state: "on"
```

## Troubleshooting

### No events detected
- Check that motion detection is enabled in the camera's web UI
- Verify `targetType` is set to `human,vehicle` in the camera's motion detection settings
- Set log level to `debug` to see all events including unclassified motion

### Connection errors
- Ensure the camera is reachable from HA (`ping <camera_ip>`)
- Verify camera credentials work in the web UI (`https://<camera_ip>/doc/index.html`)
- The add-on auto-reconnects with exponential backoff (5s → 60s)

### Entity not appearing in HA
- Verify the MQTT integration is configured in HA
- Check that the Mosquitto broker is running
- Look in HA Developer Tools → States and search for `prama`

## Supported Cameras

Tested on:
- **Prama PT-NC163D3-WNM(D2)** (firmware V5.8.5)

Should work with other Prama cameras that use the `pramaAPI` protocol with `alertStream` endpoint. The key requirement is that the camera supports `eventType=VMD` with `targetType` classification.

## Protocol Reference

See [pramaproto.md](https://github.com/shyam-prama/ha-prama-alert-bridge/blob/main/pramaproto.md) for the complete reverse-engineered Prama API documentation.
