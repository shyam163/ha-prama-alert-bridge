# Prama Camera Protocol Reference

Complete reverse-engineered protocol documentation for the Prama PT-NC163D3-WNM(D2) IP camera. This camera uses a proprietary HTTP API (`pramaAPI`) that is **not** documented publicly. Everything here was discovered through network probing, API exploration, and live testing.

## Device Info

| Field | Value |
|-------|-------|
| Model | PT-NC163D3-WNM(D2) |
| Firmware | V5.8.5 (build 250729) |
| Serial | PT-NC163D3-WNM(D2)GL870390520251210 |
| MAC | e4:28:a4:6b:88:55 |
| IP | 192.168.1.44 (DHCP) |
| Web Server | GoAhead |
| Resolution (main) | 3200x1800 (6MP) H.264 |
| Resolution (sub) | 640x360 H.264 |

## Network Services

| Port | Protocol | Service |
|------|----------|---------|
| 80 | HTTP | Redirects to HTTPS |
| 443 | HTTPS | Web UI + pramaAPI |
| 554 | RTSP | Video streaming |

## Authentication

All `/pramaAPI/` endpoints use **HTTP Digest Authentication**.

- Username: `admin`
- Password: configured per-device

The camera also supports session-based auth via `/pramaAPI/Security/sessionLogin`, but digest auth is simpler and sufficient for API access.

## API Overview

**Base URL:** `https://<camera_ip>/pramaAPI/`

**XML Namespace:** `http://www.std-cgi.com/ver20/XMLSchema` (version 2.0)

All responses are XML with this namespace. The namespace prefix must be used when parsing with tools like `xml.etree.ElementTree`.

---

## System Endpoints

### GET /pramaAPI/System/deviceInfo
Returns device information (model, serial, firmware, MAC address).

### GET /pramaAPI/System/capabilities
Returns full device capability tree covering: network, IO, video, audio, security, event types, storage.

### GET /pramaAPI/System/time
Returns current device time and timezone configuration.

---

## Streaming Endpoints

### GET /pramaAPI/streaming/channels/101
Main stream configuration (resolution, codec, quality, framerate).

### GET /pramaAPI/streaming/channels/102
Sub stream configuration.

### RTSP URLs
- **Main stream:** `rtsp://<camera_ip>:554/Streaming/Channels/101`
- **Sub stream:** `rtsp://<camera_ip>:554/Streaming/Channels/102`

### Snapshot
- `http://<camera_ip>/onvif-http/snapshot?Profile_1` (no auth required if ONVIF is enabled)

---

## Motion Detection

### GET /pramaAPI/System/Video/inputs/channels/1/motionDetection
Returns current motion detection configuration as XML.

### PUT /pramaAPI/System/Video/inputs/channels/1/motionDetection
Updates motion detection configuration. Send full XML body.

### GET /pramaAPI/System/Video/inputs/channels/1/motionDetection/capabilities
Returns motion detection capabilities (sensitivity range, grid dimensions, supported target types).

### Motion Detection Configuration XML

```xml
<MotionDetection version="2.0" xmlns="http://www.std-cgi.com/ver20/XMLSchema">
  <enabled>true</enabled>
  <enableHighlight>true</enableHighlight>
  <samplingInterval>2</samplingInterval>
  <startTriggerTime>500</startTriggerTime>
  <endTriggerTime>500</endTriggerTime>
  <regionType>grid</regionType>
  <Grid>
    <rowGranularity>18</rowGranularity>
    <columnGranularity>22</columnGranularity>
  </Grid>
  <MotionDetectionLayout>
    <sensitivityLevel>60</sensitivityLevel>
    <layout>
      <gridMap>ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff</gridMap>
    </layout>
    <targetType>human,vehicle</targetType>
  </MotionDetectionLayout>
</MotionDetection>
```

### Configuration Fields

| Field | Values | Description |
|-------|--------|-------------|
| `enabled` | true/false | Master enable for motion detection |
| `enableHighlight` | true/false | Show motion highlight overlay on stream |
| `samplingInterval` | integer | Frame sampling interval |
| `startTriggerTime` | ms | Delay before triggering alert (debounce) |
| `endTriggerTime` | ms | Delay before clearing alert |
| `sensitivityLevel` | 0-100 (step 20) | Detection sensitivity |
| `gridMap` | 108 hex chars | Detection zone grid (18 rows x 22 cols = 396 cells) |
| `targetType` | human, vehicle | Comma-separated AI classification targets |

### Grid Map Format
- 18 rows x 22 columns = 396 cells
- Encoded as 108 hexadecimal characters (396 bits / 4 = 99, padded to 108)
- Each hex char represents 4 cells: `f` = all active, `0` = all inactive
- All `f`'s = full-frame detection coverage
- All `0`'s = no detection zones

---

## Event System

### GET /pramaAPI/Event/channels/1/capabilities
Returns supported event types:
- `motionDetection` — basic motion
- `VMD` — Video Motion Detection (with AI classification)
- `tamperDetection` — camera tamper/obstruction
- `Shelteralarm` — shelter alarm
- `nicbroken` — network interface failure
- `ipconflict` — IP address conflict
- `illaccess` — illegal access attempt

### GET /pramaAPI/Event/notification/alertStream

**This is the critical endpoint for real-time AI detection.**

Long-lived HTTP connection that returns multipart XML events separated by `--boundary`. Similar to Server-Sent Events but uses multipart HTTP chunked encoding.

**Connection details:**
- Method: GET
- Auth: HTTP Digest
- SSL: HTTPS (self-signed cert, verify=False required)
- Timeout: connect=10s, read=None (infinite — it's a persistent stream)
- Response: `Transfer-Encoding: chunked`, multipart with `--boundary` separator

### Alert Stream Event Format

```
--boundary
Content-Type: application/xml; charset="UTF-8"

<EventNotificationAlert version="2.0" xmlns="http://www.std-cgi.com/ver20/XMLSchema">
  <ipAddress>0.0.0.0</ipAddress>
  <ipv6Address>::ffff:192.168.1.44</ipv6Address>
  <portNo>443</portNo>
  <protocol>HTTPS</protocol>
  <macAddress>e4:28:a4:6b:88:55</macAddress>
  <channelID>1</channelID>
  <dateTime>2026-03-22T16:26:24+05:30</dateTime>
  <activePostCount>1</activePostCount>
  <eventType>VMD</eventType>
  <eventState>active</eventState>
  <eventDescription>Motion alarm</eventDescription>
  <channelName>Camera 01</channelName>
  <targetType>human</targetType>
</EventNotificationAlert>
```

### Event Fields

| Field | Values | Description |
|-------|--------|-------------|
| `eventType` | `VMD` | Video Motion Detection (AI-classified) |
| `eventType` | `videoloss` | Video signal lost/restored |
| `eventType` | `tamperDetection` | Camera tampered |
| `eventState` | `active` | Event currently happening |
| `eventState` | `inactive` | Event ended |
| `targetType` | `human` | AI classified motion as human |
| `targetType` | `vehicle` | AI classified motion as vehicle |
| `targetType` | *(absent)* | Unclassified generic motion |
| `channelID` | `1` | Camera channel (single-channel camera) |
| `dateTime` | ISO 8601 | Event timestamp with timezone offset |
| `activePostCount` | integer | Sequential event counter |
| `macAddress` | MAC | Camera MAC address |

### Event Behavior Notes

- **VMD + human**: Fires rapidly during continuous human presence (~1-2 events/second)
- **VMD without targetType**: Generic motion (wind, animals, shadows)
- **videoloss**: Fires when camera feed is interrupted/restored
- **activePostCount**: Increments with each event, useful for detecting gaps
- Events arrive in batches (chunked encoding), not individually — parser must handle buffering
- The `--boundary` marker separates events; partial XML may span chunks
- Stream stays open indefinitely; camera may close it after extended periods of inactivity
- On disconnect, the camera does NOT send a close event — the HTTP connection simply drops

---

## Security / Session Endpoints

### GET /pramaAPI/Security/challenge
Returns an authentication challenge for session-based auth.

### POST /pramaAPI/Security/sessionLogin?timeStamp=\<unix_ms\>
Session login with credentials. Returns session token.

### POST /pramaAPI/Security/sessionLogout
Ends the current session.

### GET /pramaAPI/Security/token?format=json
Returns an auth token in JSON format.

---

## ONVIF Support

| Detail | Value |
|--------|-------|
| Endpoint | `http://<camera_ip>/onvif/device_service` |
| Default state | **Disabled** (must enable in web UI) |
| Profiles | Profile_1 (main), Profile_2 (sub) |
| Events exposed | motion, tamper |
| Events NOT exposed | **Human/vehicle detection** |

**Critical limitation:** ONVIF only exposes basic motion and tamper events. The AI-powered human/vehicle classification is **only available** through the proprietary `/pramaAPI/Event/notification/alertStream` endpoint.

When added to Home Assistant via ONVIF integration, the camera creates:
- `camera.<name>_mainstream` — main RTSP stream
- `camera.<name>_minorstream` — sub RTSP stream (if available)
- `binary_sensor.<name>_motion_alarm` — basic ONVIF motion
- `binary_sensor.<name>_cell_motion_detection` — cell-based motion
- `binary_sensor.<name>_tamper_detection` — tamper sensor

**Note:** HA names ONVIF devices from the camera's internal device name, not its IP. This camera registered as `six_mp_one` (from its internal profile name for the 6MP stream).

---

## Web UI

| Detail | Value |
|--------|-------|
| URL | `https://<camera_ip>/doc/index.html` |
| Framework | Vue.js SPA |
| Smart detection | Settings at `config/event/smartEvent/` routes |

---

## Parsing Notes for Developers

### XML Namespace Handling (Python)
```python
NS = {"ns": "http://www.std-cgi.com/ver20/XMLSchema"}
root = ET.fromstring(xml_text)
event_type = root.find("ns:eventType", NS).text
target_type = root.find("ns:targetType", NS)  # May be None
```

### Stream Parsing Strategy
1. Use `requests.get(url, stream=True, verify=False)` with digest auth
2. Read with `iter_content(chunk_size=4096, decode_unicode=True)`
3. Buffer chunks and split on `--boundary`
4. Extract XML between `<EventNotificationAlert` and `</EventNotificationAlert>`
5. Handle partial chunks: XML may span multiple chunks
6. Handle bytes vs str: `iter_content` with `decode_unicode=True` returns str, but fallback to `.decode()` on bytes

### Connection Resilience
- Camera may drop the connection after long idle periods
- Use exponential backoff on reconnect (5s → 10s → 20s → 40s → 60s max)
- Always verify SSL=False (self-signed cert)
- Set connect timeout (10s) but no read timeout (stream is persistent)
