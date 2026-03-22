# Changelog

## 1.0.0

- Initial release
- Connects to Prama camera alertStream (pramaAPI) via HTTPS with digest auth
- Parses multipart XML events for VMD (Video Motion Detection) with AI target classification
- Publishes to MQTT with Home Assistant auto-discovery
- Supports human and vehicle detection types
- Configurable occupancy timeout (off_delay)
- Auto-reconnect with exponential backoff on connection loss
- Configurable sensor name for multi-camera setups
