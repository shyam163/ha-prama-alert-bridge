#!/usr/bin/with-contenv bashio

# Read add-on options via bashio
CAMERA_HOST=$(bashio::config 'camera_host')
CAMERA_USER=$(bashio::config 'camera_username')
CAMERA_PASS=$(bashio::config 'camera_password')
MQTT_HOST=$(bashio::config 'mqtt_host')
MQTT_PORT=$(bashio::config 'mqtt_port')
MQTT_USER=$(bashio::config 'mqtt_username')
MQTT_PASS=$(bashio::config 'mqtt_password')
OFF_DELAY=$(bashio::config 'off_delay')
SENSOR_NAME=$(bashio::config 'sensor_name')
LOG_LEVEL=$(bashio::config 'log_level')

# Build detection types YAML list
DETECTION_TYPES=""
for type in $(bashio::config 'detection_types'); do
    DETECTION_TYPES="${DETECTION_TYPES}    - ${type}\n"
done

# Generate config.yaml from add-on options
cat > /app/config.yaml <<EOF
camera:
  host: "${CAMERA_HOST}"
  username: "${CAMERA_USER}"
  password: "${CAMERA_PASS}"

mqtt:
  host: "${MQTT_HOST}"
  port: ${MQTT_PORT}
  username: "${MQTT_USER}"
  password: "${MQTT_PASS}"

detection:
  types:
$(echo -e "${DETECTION_TYPES}")  off_delay: ${OFF_DELAY}

sensor_name: "${SENSOR_NAME}"
log_level: "${LOG_LEVEL}"
EOF

bashio::log.info "Prama Alert Bridge starting..."
bashio::log.info "Camera: ${CAMERA_HOST}"
bashio::log.info "MQTT: ${MQTT_HOST}:${MQTT_PORT}"
bashio::log.info "Sensor: ${SENSOR_NAME}"
bashio::log.info "Off delay: ${OFF_DELAY}s"

exec python3 /app/prama_alert_bridge.py
