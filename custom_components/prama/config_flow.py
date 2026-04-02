"""Config flow for Prama Camera integration."""

import logging
import xml.etree.ElementTree as ET

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_CAMERA_HOST,
    CONF_DETECTION_TYPES,
    CONF_OFF_DELAY,
    CONF_PRAMA_PASSWORD,
    CONF_PRAMA_USERNAME,
    CONF_SENSOR_NAME,
    DEFAULT_OFF_DELAY,
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
    import requests
    import urllib3
    from requests.auth import HTTPDigestAuth

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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


class PramaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Prama Camera."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
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
                return self.async_create_entry(
                    title=f"Prama {user_input[CONF_SENSOR_NAME]}",
                    data={
                        **user_input,
                        "device_model": device_info.get("model", "Prama IP Camera"),
                        "device_firmware": device_info.get("firmware"),
                        "device_mac": device_info.get("mac"),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CAMERA_HOST): str,
                    vol.Required(
                        CONF_PRAMA_USERNAME, default=DEFAULT_PRAMA_USERNAME
                    ): str,
                    vol.Required(CONF_PRAMA_PASSWORD): str,
                    vol.Required(CONF_SENSOR_NAME, default="prama"): str,
                    vol.Required(
                        CONF_OFF_DELAY, default=DEFAULT_OFF_DELAY
                    ): int,
                }
            ),
            errors=errors,
        )
