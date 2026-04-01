"""Constants for the Prama integration."""

DOMAIN = "prama"

# Config keys
CONF_CAMERA_HOST = "camera_host"
CONF_PRAMA_USERNAME = "prama_username"
CONF_PRAMA_PASSWORD = "prama_password"
CONF_ONVIF_ENABLED = "onvif_enabled"
CONF_ONVIF_USERNAME = "onvif_username"
CONF_ONVIF_PASSWORD = "onvif_password"
CONF_ONVIF_PORT = "onvif_port"
CONF_SENSOR_NAME = "sensor_name"
CONF_DETECTION_TYPES = "detection_types"
CONF_OFF_DELAY = "off_delay"

# Defaults
DEFAULT_PRAMA_USERNAME = "admin"
DEFAULT_ONVIF_PORT = 80
DEFAULT_OFF_DELAY = 120
DEFAULT_DETECTION_TYPES = ["human"]

# API endpoints
PRAMA_API_DEVICE_INFO = "/pramaAPI/System/deviceInfo"
PRAMA_API_ALERT_STREAM = "/pramaAPI/Event/notification/alertStream"
XML_NAMESPACE = {"ns": "http://www.std-cgi.com/ver20/XMLSchema"}

# Reconnect
MIN_RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 60
