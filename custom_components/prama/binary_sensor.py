"""Binary sensor platform for Prama camera motion detection."""

import logging
from datetime import datetime, timezone

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .alert_stream import AlertStreamManager
from .const import (
    CONF_CAMERA_HOST,
    CONF_DETECTION_TYPES,
    CONF_OFF_DELAY,
    CONF_PRAMA_PASSWORD,
    CONF_PRAMA_USERNAME,
    CONF_SENSOR_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Prama binary sensor from config entry."""
    config = hass.data[DOMAIN][entry.entry_id]["config"]

    sensor = PramaMotionBinarySensor(hass, entry, config)
    async_add_entities([sensor])

    # Create and start the alert stream manager
    stream_manager = AlertStreamManager(
        hass=hass,
        host=config[CONF_CAMERA_HOST],
        username=config[CONF_PRAMA_USERNAME],
        password=config[CONF_PRAMA_PASSWORD],
        detection_types=config[CONF_DETECTION_TYPES],
        callback=sensor.handle_alert,
    )

    # Store reference for cleanup
    hass.data[DOMAIN][entry.entry_id]["stream_manager"] = stream_manager

    # Start stream in background thread
    await hass.async_add_executor_job(stream_manager.start)
    _LOGGER.info(
        "Started alert stream for %s (%s)",
        config[CONF_SENSOR_NAME],
        config[CONF_CAMERA_HOST],
    )


class PramaMotionBinarySensor(BinarySensorEntity):
    """Binary sensor for Prama camera AI motion detection."""

    _attr_device_class = BinarySensorDeviceClass.MOTION
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, config: dict):
        self.hass = hass
        self._entry = entry
        self._sensor_name = config[CONF_SENSOR_NAME]
        self._off_delay = config[CONF_OFF_DELAY]

        self._attr_unique_id = f"prama_{self._sensor_name}_motion"
        self._attr_name = "Motion"
        self._attr_icon = "mdi:motion-sensor"
        self._attr_is_on = False

        self._last_detection_time = None
        self._target_type = None
        self._channel = None
        self._event_state = None
        self._off_timer_cancel = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to link entity to a device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.data[CONF_CAMERA_HOST])},
            name=f"Prama {self._sensor_name.replace('_', ' ').title()}",
            manufacturer="Prama",
            model=self._entry.data.get("device_model", "Prama IP Camera"),
            sw_version=self._entry.data.get("device_firmware"),
        )

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        return {
            "last_detection_time": self._last_detection_time,
            "target_type": self._target_type,
            "channel": self._channel,
            "event_state": self._event_state,
        }

    @callback
    def handle_alert(self, alert: dict):
        """Handle incoming alert from stream manager. Runs on HA event loop."""
        self._attr_is_on = True
        self._last_detection_time = (
            alert.get("date_time") or datetime.now(timezone.utc).isoformat()
        )
        self._target_type = alert.get("target_type")
        self._channel = alert.get("channel_id")
        self._event_state = alert.get("event_state")

        self.async_write_ha_state()

        # Cancel any existing off timer
        if self._off_timer_cancel is not None:
            self._off_timer_cancel()

        # Schedule auto-off after off_delay seconds
        self._off_timer_cancel = async_call_later(
            self.hass, self._off_delay, self._async_turn_off
        )

    @callback
    def _async_turn_off(self, _now=None):
        """Turn off the sensor after off_delay."""
        self._attr_is_on = False
        self._off_timer_cancel = None
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self):
        """Clean up timer when entity is removed."""
        if self._off_timer_cancel is not None:
            self._off_timer_cancel()
            self._off_timer_cancel = None
