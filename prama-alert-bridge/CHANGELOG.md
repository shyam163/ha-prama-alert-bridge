# Changelog

## 2.0.0

- **BREAKING:** Multi-camera support in a single add-on instance
- Config restructured: camera settings now in a `cameras` array
- Each camera runs in its own thread with independent reconnect backoff
- MQTT settings shared across all cameras
- Each camera gets its own sensor_name, detection_types, and off_delay
- If upgrading from 1.x, you must reconfigure the add-on

## 1.0.0

- Initial release
- Connects to Prama camera alertStream (pramaAPI) via HTTPS with digest auth
- Parses multipart XML events for VMD (Video Motion Detection) with AI target classification
- Publishes to MQTT with Home Assistant auto-discovery
- Supports human and vehicle detection types
- Configurable occupancy timeout (off_delay)
- Auto-reconnect with exponential backoff on connection loss
- Configurable sensor name for multi-camera setups
