#!/usr/bin/with-contenv bashio

# Read shared options via bashio
MQTT_HOST=$(bashio::config 'mqtt_host')
MQTT_PORT=$(bashio::config 'mqtt_port')
MQTT_USER=$(bashio::config 'mqtt_username')
MQTT_PASS=$(bashio::config 'mqtt_password')
LOG_LEVEL=$(bashio::config 'log_level')

# Build cameras YAML from JSON array
CAMERAS_YAML=""
for index in $(bashio::config 'cameras|keys[]'); do
    CAM_HOST=$(bashio::config "cameras[${index}].host")
    CAM_USER=$(bashio::config "cameras[${index}].username")
    CAM_PASS=$(bashio::config "cameras[${index}].password")
    CAM_SENSOR=$(bashio::config "cameras[${index}].sensor_name")
    CAM_OFF_DELAY=$(bashio::config "cameras[${index}].off_delay")

    # Build detection types list for this camera
    TYPES_YAML=""
    for tidx in $(bashio::config "cameras[${index}].detection_types|keys[]"); do
        type=$(bashio::config "cameras[${index}].detection_types[${tidx}]")
        TYPES_YAML="${TYPES_YAML}      - ${type}
"
    done

    CAMERAS_YAML="${CAMERAS_YAML}  - host: \"${CAM_HOST}\"
    username: \"${CAM_USER}\"
    password: \"${CAM_PASS}\"
    sensor_name: \"${CAM_SENSOR}\"
    detection_types:
${TYPES_YAML}    off_delay: ${CAM_OFF_DELAY}
"
    bashio::log.info "Camera ${index}: ${CAM_HOST} (sensor: ${CAM_SENSOR})"
done

# Generate config.yaml from add-on options
cat > /app/config.yaml <<ENDOFCONFIG
mqtt:
  host: "${MQTT_HOST}"
  port: ${MQTT_PORT}
  username: "${MQTT_USER}"
  password: "${MQTT_PASS}"

cameras:
${CAMERAS_YAML}
log_level: "${LOG_LEVEL}"
ENDOFCONFIG

bashio::log.info "Generated config.yaml:"
cat /app/config.yaml

bashio::log.info "Prama Alert Bridge starting..."
bashio::log.info "MQTT: ${MQTT_HOST}:${MQTT_PORT}"

exec python3 /app/prama_alert_bridge.py
