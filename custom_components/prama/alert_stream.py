"""Alert stream manager for Prama cameras.

Connects to the pramaAPI alertStream endpoint, parses multipart XML events,
and fires callbacks on the HA event loop when matching detections occur.
"""

import logging
import threading
import time
import xml.etree.ElementTree as ET

import requests
import urllib3
from requests.auth import HTTPDigestAuth

from .const import (
    MAX_RECONNECT_DELAY,
    MIN_RECONNECT_DELAY,
    PRAMA_API_ALERT_STREAM,
    XML_NAMESPACE,
)

_LOGGER = logging.getLogger(__name__)

# Prama cameras use self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def parse_alert_xml(xml_text):
    """Parse an EventNotificationAlert XML block, return dict or None."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    def get(tag):
        el = root.find(f"ns:{tag}", XML_NAMESPACE)
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


class AlertStreamManager:
    """Manages long-lived HTTPS connection to Prama alertStream."""

    def __init__(self, hass, host, username, password, detection_types, callback):
        self._hass = hass
        self._host = host
        self._username = username
        self._password = password
        self._detection_types = set(detection_types)
        self._callback = callback
        self._stop_event = threading.Event()
        self._thread = None
        self._connected = False

    @property
    def connected(self):
        """Return True if currently connected to alert stream."""
        return self._connected

    def start(self):
        """Start the alert stream in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"prama-stream-{self._host}",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        """Signal the stream to stop and wait for thread exit."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None

    def _run_loop(self):
        """Reconnect loop with exponential backoff."""
        backoff = MIN_RECONNECT_DELAY
        while not self._stop_event.is_set():
            try:
                self._stream_alerts()
                backoff = MIN_RECONNECT_DELAY
            except requests.exceptions.RequestException as e:
                _LOGGER.error("Stream connection error for %s: %s", self._host, e)
            except Exception:
                _LOGGER.exception("Unexpected error streaming from %s", self._host)
            finally:
                self._connected = False

            if self._stop_event.is_set():
                break

            _LOGGER.info("Reconnecting to %s in %ds", self._host, backoff)
            for _ in range(backoff):
                if self._stop_event.is_set():
                    return
                time.sleep(1)
            backoff = min(backoff * 2, MAX_RECONNECT_DELAY)

    def _stream_alerts(self):
        """Connect and process alert stream. Blocks until disconnect."""
        url = f"https://{self._host}{PRAMA_API_ALERT_STREAM}"
        auth = HTTPDigestAuth(self._username, self._password)

        response = requests.get(
            url, auth=auth, stream=True, verify=False, timeout=(10, 30)
        )
        response.raise_for_status()
        self._connected = True
        _LOGGER.info("Alert stream connected to %s (HTTP %d)", self._host, response.status_code)

        buffer = ""
        for chunk in response.iter_content(chunk_size=4096, decode_unicode=True):
            if self._stop_event.is_set():
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

                alert = self._parse_event_block(event_block)
                if alert is None:
                    continue

                if alert["event_type"] != "VMD":
                    continue
                if alert["target_type"] not in self._detection_types:
                    continue

                # Fire callback on HA event loop
                self._hass.loop.call_soon_threadsafe(self._callback, alert)

    @staticmethod
    def _parse_event_block(event_block):
        """Extract and parse XML from an event block."""
        xml_start = event_block.find("<EventNotificationAlert")
        xml_end = event_block.find("</EventNotificationAlert>")
        if xml_start == -1 or xml_end == -1:
            return None
        xml_text = event_block[xml_start : xml_end + len("</EventNotificationAlert>")]
        return parse_alert_xml(xml_text)
