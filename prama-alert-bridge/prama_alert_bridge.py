#!/usr/bin/env python3
"""Prama Camera Alert Stream → MQTT Bridge for Home Assistant.

Connects to one or more Prama camera alertStream endpoints,
parses XML events for human/vehicle detection, and publishes to MQTT
with HA auto-discovery so binary_sensors are created automatically.

Compatible with Prama cameras using the pramaAPI protocol
(tested on PT-NC163D3-WNM(D2) and PT-NC140D7-WNMS/AW(D2), firmware V5.8.5).
"""

import json
import logging
import signal
import sys
import threading
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


def setup_mqtt(config):
    """Connect to MQTT broker. Returns the shared client."""
    client = mqtt.Client(client_id="prama_alert_bridge", protocol=mqtt.MQTTv311)
    mqtt_cfg = config["mqtt"]

    if mqtt_cfg.get("username"):
        client.username_pw_set(mqtt_cfg["username"], mqtt_cfg.get("password", ""))

    client.connect(mqtt_cfg["host"], mqtt_cfg.get("port", 1883), keepalive=60)
    client.loop_start()
    log.info("MQTT connected to %s:%s", mqtt_cfg["host"], mqtt_cfg.get("port", 1883))
    return client


def publish_camera_discovery(mqtt_client, cam_cfg):
    """Publish HA MQTT auto-discovery config for one camera. Returns topics dict."""
    sensor_name = cam_cfg["sensor_name"]
    state_topic = f"prama/{sensor_name}/motion/state"
    attr_topic = f"prama/{sensor_name}/motion/attributes"
    avail_topic = f"prama/{sensor_name}/motion/availability"
    discovery_topic = f"homeassistant/binary_sensor/prama_{sensor_name}/config"

    off_delay = cam_cfg.get("off_delay", 120)
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

    mqtt_client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)
    mqtt_client.publish(avail_topic, "online", retain=True)
    log.info(
        "[%s] Discovery config published (off_delay=%ds)", sensor_name, off_delay
    )

    return {
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


def stream_alerts(cam_cfg, mqtt_client, topics):
    """Connect to one camera's alertStream and process events. Returns on disconnect."""
    sensor_name = cam_cfg["sensor_name"]
    url = f"https://{cam_cfg['host']}/pramaAPI/Event/notification/alertStream"
    auth = HTTPDigestAuth(cam_cfg["username"], cam_cfg["password"])

    raw_types = cam_cfg.get("detection_types", ["human"])
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

    log.info("[%s] Connecting to alert stream at %s", sensor_name, cam_cfg["host"])

    response = requests.get(
        url, auth=auth, stream=True, verify=False, timeout=(10, 30)
    )
    response.raise_for_status()
    log.info("[%s] Alert stream connected (HTTP %d)", sensor_name, response.status_code)

    buffer = ""
    for chunk in response.iter_content(chunk_size=4096, decode_unicode=True):
        if not running:
            break

        if chunk is None:
            continue

        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8", errors="replace")

        buffer += chunk

        while "--boundary" in buffer:
            parts = buffer.split("--boundary", 1)
            event_block = parts[0]
            buffer = parts[1] if len(parts) > 1 else ""

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
                "[%s] Event: type=%s state=%s target=%s",
                sensor_name,
                alert["event_type"],
                alert["event_state"],
                alert["target_type"],
            )

            if alert["event_type"] != "VMD":
                continue
            if alert["target_type"] not in detection_types:
                continue

            mqtt_client.publish(topics["state"], "ON")

            attrs = {
                "last_detection_time": alert["date_time"]
                or datetime.now(timezone.utc).isoformat(),
                "target_type": alert["target_type"],
                "channel": alert["channel_id"],
                "event_state": alert["event_state"],
            }
            mqtt_client.publish(topics["attributes"], json.dumps(attrs))

            log.info(
                "[%s] %s detected! Published ON (target=%s, time=%s)",
                sensor_name,
                alert["target_type"].capitalize(),
                alert["target_type"],
                alert["date_time"],
            )


def camera_thread(cam_cfg, mqtt_client):
    """Run stream_alerts in a reconnect loop for one camera."""
    sensor_name = cam_cfg["sensor_name"]
    topics = publish_camera_discovery(mqtt_client, cam_cfg)
    backoff = 5
    max_backoff = 60

    try:
        while running:
            try:
                stream_alerts(cam_cfg, mqtt_client, topics)
                backoff = 5
            except requests.exceptions.RequestException as e:
                log.error("[%s] Stream connection error: %s", sensor_name, e)
            except Exception as e:
                log.error("[%s] Unexpected error: %s", sensor_name, e, exc_info=True)

            if not running:
                break

            log.info("[%s] Reconnecting in %ds...", sensor_name, backoff)
            for _ in range(backoff):
                if not running:
                    break
                time.sleep(1)
            backoff = min(backoff * 2, max_backoff)
    finally:
        mqtt_client.publish(topics["availability"], "offline", retain=True)
        log.info("[%s] Camera thread stopped", sensor_name)


def main():
    config = load_config()

    global log
    log = setup_logging(config)

    mqtt_client = setup_mqtt(config)

    cameras = config.get("cameras", [])
    if not cameras:
        log.error("No cameras configured")
        return

    log.info("Starting bridge for %d camera(s)", len(cameras))

    threads = []
    for cam_cfg in cameras:
        t = threading.Thread(
            target=camera_thread,
            args=(cam_cfg, mqtt_client),
            name=f"cam-{cam_cfg['sensor_name']}",
            daemon=True,
        )
        t.start()
        threads.append(t)
        log.info(
            "Started thread for camera %s (%s)",
            cam_cfg["sensor_name"],
            cam_cfg["host"],
        )

    try:
        while running:
            time.sleep(1)
    finally:
        global running
        running = False
        for t in threads:
            t.join(timeout=10)
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        log.info("Bridge stopped")


if __name__ == "__main__":
    main()
