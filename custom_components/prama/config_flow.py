"""Config flow for Prama Camera integration."""

import logging
import xml.etree.ElementTree as ET

import requests
import voluptuous as vol
from requests.auth import HTTPDigestAuth

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_CAMERA_HOST,
    CONF_DETECTION_TYPES,
    CONF_OFF_DELAY,
    CONF_ONVIF_ENABLED,
    CONF_ONVIF_PASSWORD,
    CONF_ONVIF_PORT,
    CONF_ONVIF_USERNAME,
    CONF_PRAMA_PASSWORD,
    CONF_PRAMA_USERNAME,
    CONF_SENSOR_NAME,
    DEFAULT_OFF_DELAY,
    DEFAULT_ONVIF_PORT,
    DEFAULT_PRAMA_USERNAME,
    DOMAIN,
    PRAMA_API_DEVICE_INFO,
    XML_NAMESPACE,
)

_LOGGER = logging.getLogger(__name__)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


def validate_prama_credentials(host, username, password):
    """Test pramaAPI connection. Returns device info dict. Blocking call."""
    url = f"https://{host}{PRAMA_API_DEVICE_INFO}"
    try:
        resp = requests.get(
            url,
            auth=HTTPDigestAuth(username, password),
            verify=False,
            timeout=10,
        )
    except requests.exceptions.ConnectionError as err:
        raise CannotConnect(f"Cannot connect to {host}") from err
    except requests.exceptions.Timeout as err:
        raise CannotConnect(f"Timeout connecting to {host}") from err

    if resp.status_code == 401:
        raise InvalidAuth("Invalid pramaAPI credentials")
    resp.raise_for_status()

    # Parse XML for model and firmware
    try:
        root = ET.fromstring(resp.text)
        model_el = root.find("ns:model", XML_NAMESPACE)
        fw_el = root.find("ns:firmwareVersion", XML_NAMESPACE)
        mac_el = root.find("ns:macAddress", XML_NAMESPACE)
        return {
            "model": model_el.text if model_el is not None else "Unknown",
            "firmware": fw_el.text if fw_el is not None else "Unknown",
            "mac": mac_el.text if mac_el is not None else None,
        }
    except ET.ParseError as err:
        raise CannotConnect("Invalid response from camera") from err


def validate_onvif_credentials(host, port, username, password):
    """Test ONVIF connection. Returns True on success. Blocking call."""
    url = f"http://{host}:{port}/onvif/device_service"
    try:
        resp = requests.get(url, timeout=5)
        return resp.status_code < 500
    except requests.exceptions.RequestException:
        return False


class PramaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Prama Camera."""

    VERSION = 1

    def __init__(self):
        """Initialize flow."""
        self._host = None
        self._prama_user = None
        self._prama_pass = None
        self._device_info = {}
        self._onvif_data = {}

    async def async_step_user(self, user_input=None):
        """Step 1: Camera host and pramaAPI credentials."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_CAMERA_HOST]
            username = user_input[CONF_PRAMA_USERNAME]
            password = user_input[CONF_PRAMA_PASSWORD]

            try:
                device_info = await self.hass.async_add_executor_job(
                    validate_prama_credentials, host, username, password
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error validating Prama credentials")
                errors["base"] = "unknown"
            else:
                # Check for duplicate
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()

                self._host = host
                self._prama_user = username
                self._prama_pass = password
                self._device_info = device_info
                return await self.async_step_onvif()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CAMERA_HOST): str,
                    vol.Required(
                        CONF_PRAMA_USERNAME, default=DEFAULT_PRAMA_USERNAME
                    ): str,
                    vol.Required(CONF_PRAMA_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_onvif(self, user_input=None):
        """Step 2: Optional ONVIF credentials."""
        errors = {}

        if user_input is not None:
            if user_input.get(CONF_ONVIF_ENABLED, False):
                onvif_ok = await self.hass.async_add_executor_job(
                    validate_onvif_credentials,
                    self._host,
                    user_input.get(CONF_ONVIF_PORT, DEFAULT_ONVIF_PORT),
                    user_input.get(CONF_ONVIF_USERNAME, ""),
                    user_input.get(CONF_ONVIF_PASSWORD, ""),
                )
                if not onvif_ok:
                    errors["base"] = "onvif_failed"
                else:
                    self._onvif_data = {
                        CONF_ONVIF_ENABLED: True,
                        CONF_ONVIF_USERNAME: user_input.get(CONF_ONVIF_USERNAME, ""),
                        CONF_ONVIF_PASSWORD: user_input.get(CONF_ONVIF_PASSWORD, ""),
                        CONF_ONVIF_PORT: user_input.get(
                            CONF_ONVIF_PORT, DEFAULT_ONVIF_PORT
                        ),
                    }
                    return await self.async_step_sensors()
            else:
                self._onvif_data = {CONF_ONVIF_ENABLED: False}
                return await self.async_step_sensors()

        return self.async_show_form(
            step_id="onvif",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ONVIF_ENABLED, default=False): bool,
                    vol.Optional(CONF_ONVIF_USERNAME, default=""): str,
                    vol.Optional(CONF_ONVIF_PASSWORD, default=""): str,
                    vol.Optional(
                        CONF_ONVIF_PORT, default=DEFAULT_ONVIF_PORT
                    ): int,
                }
            ),
            errors=errors,
        )

    async def async_step_sensors(self, user_input=None):
        """Step 3: Sensor settings."""
        if user_input is not None:
            # Build final config entry data
            data = {
                CONF_CAMERA_HOST: self._host,
                CONF_PRAMA_USERNAME: self._prama_user,
                CONF_PRAMA_PASSWORD: self._prama_pass,
                CONF_SENSOR_NAME: user_input[CONF_SENSOR_NAME],
                CONF_DETECTION_TYPES: user_input[CONF_DETECTION_TYPES],
                CONF_OFF_DELAY: user_input[CONF_OFF_DELAY],
                "device_model": self._device_info.get("model", "Prama IP Camera"),
                "device_firmware": self._device_info.get("firmware"),
                "device_mac": self._device_info.get("mac"),
                **self._onvif_data,
            }

            sensor_name = user_input[CONF_SENSOR_NAME]
            return self.async_create_entry(
                title=f"Prama {sensor_name}",
                data=data,
            )

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SENSOR_NAME, default="prama"): str,
                    vol.Required(
                        CONF_DETECTION_TYPES, default=["human"]
                    ): vol.All(
                        [vol.In(["human", "vehicle"])],
                        vol.Length(min=1),
                    ),
                    vol.Required(
                        CONF_OFF_DELAY, default=DEFAULT_OFF_DELAY
                    ): vol.All(int, vol.Range(min=10, max=600)),
                }
            ),
            description_placeholders={
                "model": self._device_info.get("model", "Unknown"),
                "firmware": self._device_info.get("firmware", "Unknown"),
            },
        )
