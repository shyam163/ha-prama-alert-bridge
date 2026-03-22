#!/usr/bin/env python3
"""Prama Camera Alert Stream → MQTT Bridge for Home Assistant.

Connects to the Prama camera's proprietary alertStream endpoint,
parses XML events for human/vehicle detection, and publishes to MQTT
with HA auto-discovery so the binary_sensor is created automatically.

Compatible with Prama cameras using the pramaAPI protocol
(tested on PT-NC163D3-WNM(D2), firmware V5.8.5).
"""

import json
import logging
import signal
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import requests
import yaml
from requests.auth import HTTPDigestAuth

# XML namespace used by pramaAPI
NS = {"ns": "http://www.std-cgi.com/ver20/XMLSchema"}

running = True


def signal_handler(sig, frame):
    global running
    log.info("Shutdown signal received")
    running = False


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def load_config(path="config.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)


def setup_logging(config):
    level = getattr(logging, config.get("log_level", "info").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )
    return logging.getLogger("prama_bridge")


def setup_mqtt(config, sensor_name):
    """Connect to MQTT broker and publish HA auto-discovery config."""
    client = mqtt.Client(
        client_id=f"prama_alert_bridge_{sensor_name}", protocol=mqtt.MQTTv311
    )
    mqtt_cfg = config["mqtt"]

    if mqtt_cfg.get("username"):
        client.username_pw_set(mqtt_cfg["username"], mqtt_cfg.get("password", ""))

    state_topic = f"prama/{sensor_name}/motion/state"
    attr_topic = f"prama/{sensor_name}/motion/attributes"
    avail_topic = f"prama/{sensor_name}/motion/availability"
    discovery_topic = f"homeassistant/binary_sensor/prama_{sensor_name}/config"

    client.will_set(avail_topic, "offline", retain=True)
    client.connect(mqtt_cfg["host"], mqtt_cfg.get("port", 1883), keepalive=60)
    client.loop_start()

    # Publish HA MQTT auto-discovery config (retained)
    off_delay = config.get("detection", {}).get("off_delay", 120)
    friendly_name = sensor_name.replace("_", " ").title()

    discovery_payload = {
        "name": f"Motion Detected With Occupancy Timeout {friendly_name}",
        "unique_id": f"prama_{sensor_name}_human_motion",
        "device_class": "motion",
        "state_topic": state_topic,
        "json_attributes_topic": attr_topic,
        "availability_topic": avail_topic,
        "payload_on": "ON",
        "payload_available": "online",
        "payload_not_available": "offline",
        "off_delay": off_delay,
        "icon": "mdi:motion-sensor",
        "device": {
            "identifiers": [f"prama_{sensor_name}"],
            "name": f"Prama Camera {friendly_name}",
            "model": "Prama IP Camera",
            "manufacturer": "Prama",
        },
    }

    client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)
    client.publish(avail_topic, "online", retain=True)
    log.info("MQTT connected, discovery config published (off_delay=%ds)", off_delay)

    return client, {
        "state": state_topic,
        "attributes": attr_topic,
        "availability": avail_topic,
    }


def parse_alert_xml(xml_text):
    """Parse an EventNotificationAlert XML block, return dict or None."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    def get(tag):
        el = root.find(f"ns:{tag}", NS)
        return el.text if el is not None else None

    event_type = get("eventType")
    if event_type is None:
        return None

    return {
        "event_type": event_type,
        "event_state": get("eventState"),
        "target_type": get("targetType"),
        "channel_id": get("channelID"),
        "date_time": get("dateTime"),
        "description": get("eventDescription"),
    }


def stream_alerts(config, mqtt_client, topics):
    """Connect to alertStream and process events. Returns on disconnect."""
    cam = config["camera"]
    url = f"https://{cam['host']}/pramaAPI/Event/notification/alertStream"
    auth = HTTPDigestAuth(cam["username"], cam["password"])
    raw_types = config.get("detection", {}).get("types", ["human"])
    # Handle types being strings, dicts, or nested structures from YAML parsing
    detection_types = set()
    if isinstance(raw_types, list):
        for t in raw_types:
            if isinstance(t, str):
                detection_types.add(t)
            elif isinstance(t, dict):
                detection_types.update(t.values())
    elif isinstance(raw_types, str):
        detection_types = {t.strip() for t in raw_types.split(",")}
    else:
        detection_types = {"human"}

    log.info("Connecting to alert stream at %s", cam["host"])

    response = requests.get(
        url, auth=auth, stream=True, verify=False, timeout=(10, None)
    )
    response.raise_for_status()
    log.info("Alert stream connected (HTTP %d)", response.status_code)

    buffer = ""
    for chunk in response.iter_content(chunk_size=4096, decode_unicode=True):
        if not running:
            break

        if chunk is None:
            continue

        # Handle bytes vs str
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8", errors="replace")

        buffer += chunk

        # Split on boundary markers
        while "--boundary" in buffer:
            parts = buffer.split("--boundary", 1)
            event_block = parts[0]
            buffer = parts[1] if len(parts) > 1 else ""

            # Extract XML from the event block
            xml_start = event_block.find("<EventNotificationAlert")
            xml_end = event_block.find("</EventNotificationAlert>")
            if xml_start == -1 or xml_end == -1:
                continue

            xml_text = event_block[
                xml_start : xml_end + len("</EventNotificationAlert>")
            ]
            alert = parse_alert_xml(xml_text)
            if alert is None:
                continue

            log.debug(
                "Event: type=%s state=%s target=%s",
                alert["event_type"],
                alert["event_state"],
                alert["target_type"],
            )

            # Only act on VMD events with matching target type
            if alert["event_type"] != "VMD":
                continue
            if alert["target_type"] not in detection_types:
                continue

            # Publish ON state
            mqtt_client.publish(topics["state"], "ON")

            # Publish attributes
            attrs = {
                "last_detection_time": alert["date_time"]
                or datetime.now(timezone.utc).isoformat(),
                "target_type": alert["target_type"],
                "channel": alert["channel_id"],
                "event_state": alert["event_state"],
            }
            mqtt_client.publish(topics["attributes"], json.dumps(attrs))

            log.info(
                "%s detected! Published ON (target=%s, time=%s)",
                alert["target_type"].capitalize(),
                alert["target_type"],
                alert["date_time"],
            )


def main():
    config = load_config()

    global log
    log = setup_logging(config)

    sensor_name = config.get("sensor_name", "prama")
    mqtt_client, topics = setup_mqtt(config, sensor_name)

    backoff = 5
    max_backoff = 60

    try:
        while running:
            try:
                stream_alerts(config, mqtt_client, topics)
                backoff = 5  # Reset on clean disconnect
            except requests.exceptions.RequestException as e:
                log.error("Stream connection error: %s", e)
            except Exception as e:
                log.error("Unexpected error: %s", e, exc_info=True)

            if not running:
                break

            log.info("Reconnecting in %ds...", backoff)
            # Sleep in small increments so we can respond to shutdown signals
            for _ in range(backoff):
                if not running:
                    break
                time.sleep(1)
            backoff = min(backoff * 2, max_backoff)
    finally:
        mqtt_client.publish(topics["availability"], "offline", retain=True)
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        log.info("Bridge stopped")


if __name__ == "__main__":
    main()
