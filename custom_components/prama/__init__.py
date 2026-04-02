"""The Prama Camera integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CAMERA_HOST,
    CONF_PRAMA_PASSWORD,
    CONF_PRAMA_USERNAME,
    CONF_SENSOR_NAME,
    DOMAIN,
    PRAMA_API_DEVICE_INFO,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Prama from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    config = dict(entry.data)

    # Validate credentials on startup
    await _validate_on_startup(hass, config)

    hass.data[DOMAIN][entry.entry_id] = {
        "config": config,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id, {})
        stream_manager = data.get("stream_manager")
        if stream_manager is not None:
            await hass.async_add_executor_job(stream_manager.stop)

    return unload_ok


async def _validate_on_startup(hass: HomeAssistant, config: dict):
    """Validate camera credentials on startup, log results."""
    host = config.get(CONF_CAMERA_HOST)
    sensor_name = config.get(CONF_SENSOR_NAME, host)

    if not host:
        _LOGGER.warning("[%s] No camera host configured", sensor_name)
        return

    def _test_prama():
        import requests
        import urllib3
        from requests.auth import HTTPDigestAuth

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        url = f"https://{host}{PRAMA_API_DEVICE_INFO}"
        try:
            resp = requests.get(
                url,
                auth=HTTPDigestAuth(
                    config.get(CONF_PRAMA_USERNAME, "admin"),
                    config.get(CONF_PRAMA_PASSWORD, ""),
                ),
                verify=False,
                timeout=10,
            )
            if resp.status_code == 200:
                return True, "OK"
            return False, f"HTTP {resp.status_code}"
        except requests.exceptions.RequestException as e:
            return False, str(e)

    try:
        prama_ok, prama_msg = await hass.async_add_executor_job(_test_prama)
        api_mark = "OK" if prama_ok else f"FAIL ({prama_msg})"
        _LOGGER.info("[%s] Startup check: pramaAPI=%s", sensor_name, api_mark)
    except Exception:
        _LOGGER.exception("[%s] Startup validation error", sensor_name)
