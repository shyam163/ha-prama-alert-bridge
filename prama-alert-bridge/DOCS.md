# Prama Alert Bridge

## Overview

This add-on bridges **one or more Prama cameras' AI-powered human and vehicle detection** to Home Assistant via MQTT. Prama cameras (e.g., PT-NC163D3-WNM(D2), PT-NC140D7-WNMS/AW(D2)) have on-device AI that classifies motion targets, but this data is only available through a proprietary HTTP API — not through standard protocols like ONVIF.

The add-on connects to each camera's alert stream in parallel, filters for the detection types you care about, and publishes events to MQTT with Home Assistant auto-discovery. Each camera gets its own `binary_sensor` entity.

## How It Works

```
Prama Camera 1  ─┐              This Add-on                Home Assistant
                  ├─ HTTPS ──→  ┌────────────────┐  MQTT   ┌─────────────┐
Prama Camera 2  ─┘  multipart  │ Thread per cam  │────────→│ Mosquitto   │
                     XML events │ Parse XML       │         │ Broker      │
                                │ Filter VMD      │  auto   │             │
                                │ Publish ON      │ discov. │ binary_     │
                                │                 │────────→│ sensor.*    │
                                └────────────────┘         └─────────────┘
```

1. Connects to `https://<camera>/pramaAPI/Event/notification/alertStream` with HTTP Digest Auth
2. Runs one thread per camera, each with independent reconnect backoff
3. Reads the multipart chunked response, splits on `--boundary`, parses XML
4. Filters for `eventType=VMD` with matching `targetType` (human/vehicle)
5. Publishes `ON` to MQTT state topic on each detection
6. Home Assistant auto-creates the `binary_sensor` via MQTT discovery
7. The sensor auto-turns OFF after the configured timeout (off_delay)

## Prerequisites

- **Prama IP camera(s)** with AI detection capability
- **Mosquitto MQTT broker** add-on installed and running in Home Assistant
- **MQTT integration** configured in Home Assistant
- Camera(s) must be reachable from Home Assistant over the network

## Configuration

### Cameras

Add one or more cameras to the list. Each camera has its own settings:

#### Camera Host
The IP address of your Prama camera (e.g., `192.168.1.44`). The camera must be reachable via HTTPS on port 443.

#### Camera Credentials
The admin username and password for your camera. These are the same credentials you use to log into the camera's web UI.

#### Sensor Name
A short unique identifier for this camera. Used in the entity ID and MQTT topics. Default: `prama`.

- Entity created: `binary_sensor.motion_detected_with_occupancy_timeout_<sensor_name>`
- MQTT topics: `prama/<sensor_name>/motion/state`

**Must be unique per camera.** Examples: `prama_front`, `prama_back`, `prama_6mp`.

#### Detection Types
Choose which AI detection types to bridge per camera:
- **human** — triggers on people
- **vehicle** — triggers on cars, trucks, motorcycles

#### Off Delay
The occupancy timeout in seconds (default: 120). The sensor stays ON as long as detections keep arriving. Once no detection is received for this many seconds, the sensor turns OFF.

### MQTT Settings
Shared across all cameras. Point to your MQTT broker. If you're using the Mosquitto add-on in HA, the host is your Home Assistant IP address (e.g., `192.168.1.20`), port 1883.

## Multi-Camera Setup

Add multiple entries to the **Cameras** list in the configuration. Each camera runs in its own thread with independent reconnect — if one camera goes offline, the others continue normally.

Example with two cameras:
- Camera 1: host `192.168.1.44`, sensor_name `prama_6mp`
- Camera 2: host `192.168.1.35`, sensor_name `prama_4mp`

This creates two independent binary_sensor entities.

## Entities Created

Per camera, the add-on auto-creates via MQTT discovery:

**Entity ID:** `binary_sensor.motion_detected_with_occupancy_timeout_<sensor_name>`

**Attributes:**
| Attribute | Description |
|-----------|-------------|
| `last_detection_time` | ISO 8601 timestamp of last detection |
| `target_type` | `human` or `vehicle` |
| `channel` | Camera channel ID |
| `event_state` | `active` or `inactive` |

## Troubleshooting

### No events detected
- Check that motion detection is enabled in the camera's web UI
- Verify `targetType` is set to `human,vehicle` in the camera's motion detection settings
- Set log level to `debug` to see all events including unclassified motion

### Connection errors
- Ensure the camera is reachable from HA (`ping <camera_ip>`)
- Verify camera credentials work in the web UI (`https://<camera_ip>/doc/index.html`)
- The add-on auto-reconnects with exponential backoff (5s → 60s) per camera

### Entity not appearing in HA
- Verify the MQTT integration is configured in HA
- Check that the Mosquitto broker is running
- Look in HA Developer Tools → States and search for `prama`

## Supported Cameras

Tested on:
- **Prama PT-NC163D3-WNM(D2)** (6MP, firmware V5.8.5)
- **Prama PT-NC140D7-WNMS/AW(D2)** (4MP, firmware V5.8.5)

Should work with other Prama cameras that use the `pramaAPI` protocol with `alertStream` endpoint.

## Upgrading from 1.x

Version 2.0.0 is a **breaking change**. The configuration structure changed from flat camera fields to a `cameras` array. After upgrading, you must reconfigure the add-on through the UI.

## Protocol Reference

See [pramaproto.md](https://github.com/shyam163/ha-prama-alert-bridge/blob/main/pramaproto.md) for the complete reverse-engineered Prama API documentation.
