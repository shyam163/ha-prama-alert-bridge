"""The Prama Camera integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CAMERA_HOST,
    CONF_ONVIF_ENABLED,
    CONF_ONVIF_PASSWORD,
    CONF_ONVIF_PORT,
    CONF_ONVIF_USERNAME,
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

    # Optional: auto-register ONVIF integration for this camera
    if entry.data.get(CONF_ONVIF_ENABLED):
        await _maybe_setup_onvif(hass, entry)

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
    """Validate camera and MQTT credentials on startup, log results."""
    import requests
    from requests.auth import HTTPDigestAuth

    host = config[CONF_CAMERA_HOST]
    sensor_name = config.get(CONF_SENSOR_NAME, host)

    # Test pramaAPI
    def _test_prama():
        url = f"https://{host}{PRAMA_API_DEVICE_INFO}"
        try:
            resp = requests.get(
                url,
                auth=HTTPDigestAuth(
                    config[CONF_PRAMA_USERNAME], config[CONF_PRAMA_PASSWORD]
                ),
                verify=False,
                timeout=10,
            )
            if resp.status_code == 200:
                return True, "OK"
            return False, f"HTTP {resp.status_code}"
        except requests.exceptions.RequestException as e:
            return False, str(e)

    prama_ok, prama_msg = await hass.async_add_executor_job(_test_prama)

    # Test ONVIF if enabled
    onvif_status = "skipped"
    if config.get(CONF_ONVIF_ENABLED):

        def _test_onvif():
            try:
                resp = requests.get(
                    f"http://{host}:{config.get(CONF_ONVIF_PORT, 80)}/onvif/device_service",
                    timeout=5,
                )
                return "OK" if resp.status_code < 500 else f"HTTP {resp.status_code}"
            except requests.exceptions.RequestException as e:
                return str(e)

        onvif_status = await hass.async_add_executor_job(_test_onvif)

    # Log summary
    api_mark = "OK" if prama_ok else f"FAIL ({prama_msg})"
    _LOGGER.info(
        "[%s] Startup check: pramaAPI=%s  ONVIF=%s",
        sensor_name,
        api_mark,
        onvif_status,
    )


async def _maybe_setup_onvif(hass: HomeAssistant, entry: ConfigEntry):
    """Auto-register ONVIF integration for this camera if not already present."""
    host = entry.data[CONF_CAMERA_HOST]

    # Check if an ONVIF config entry already exists for this host
    for existing_entry in hass.config_entries.async_entries("onvif"):
        if existing_entry.data.get("host") == host:
            _LOGGER.info(
                "ONVIF integration already exists for %s, skipping auto-register",
                host,
            )
            return

    try:
        result = await hass.config_entries.flow.async_init(
            "onvif",
            context={"source": "integration_discovery"},
            data={
                "host": host,
                "port": entry.data.get(CONF_ONVIF_PORT, 80),
                "username": entry.data.get(CONF_ONVIF_USERNAME, ""),
                "password": entry.data.get(CONF_ONVIF_PASSWORD, ""),
                "name": f"Prama {entry.data.get(CONF_SENSOR_NAME, host)}",
            },
        )
        _LOGGER.info("ONVIF auto-registration initiated for %s: %s", host, result)
    except Exception:
        _LOGGER.warning(
            "Could not auto-register ONVIF for %s. "
            "Add it manually via Settings > Integrations > ONVIF.",
            host,
            exc_info=True,
        )
