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
    from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_PORT, CONF_USERNAME

    host = entry.data[CONF_CAMERA_HOST]
    sensor_name = entry.data.get(CONF_SENSOR_NAME, host)

    # Check if an ONVIF config entry already exists for this host
    for existing_entry in hass.config_entries.async_entries("onvif"):
        if existing_entry.data.get("host") == host:
            _LOGGER.info(
                "ONVIF integration already exists for %s, skipping auto-register",
                host,
            )
            return

    try:
        # Step 1: Init ONVIF flow with user source, choose manual (auto=False)
        result = await hass.config_entries.flow.async_init(
            "onvif",
            context={"source": "user"},
        )

        if result.get("type") != "form":
            _LOGGER.warning("ONVIF flow init returned unexpected type: %s", result)
            return

        flow_id = result["flow_id"]

        # Step 1b: Submit auto=False to go to manual configure step
        result = await hass.config_entries.flow.async_configure(
            flow_id, user_input={"auto": False}
        )

        if result.get("type") != "form" or result.get("step_id") != "configure":
            _LOGGER.warning("ONVIF flow did not reach configure step: %s", result)
            return

        # Step 2: Submit camera details to the configure step
        result = await hass.config_entries.flow.async_configure(
            flow_id,
            user_input={
                CONF_NAME: f"Prama {sensor_name}",
                CONF_HOST: host,
                CONF_PORT: entry.data.get(CONF_ONVIF_PORT, 80),
                CONF_USERNAME: entry.data.get(CONF_ONVIF_USERNAME, ""),
                CONF_PASSWORD: entry.data.get(CONF_ONVIF_PASSWORD, ""),
            },
        )

        if result.get("type") == "create_entry":
            _LOGGER.info(
                "ONVIF auto-registration successful for %s: %s",
                host,
                result.get("title"),
            )
        elif result.get("type") == "form" and result.get("errors"):
            _LOGGER.warning(
                "ONVIF auto-registration failed for %s: %s. "
                "Add it manually via Settings > Integrations > ONVIF.",
                host,
                result.get("errors"),
            )
        else:
            _LOGGER.info("ONVIF flow result for %s: %s", host, result)

    except Exception:
        _LOGGER.warning(
            "Could not auto-register ONVIF for %s. "
            "Add it manually via Settings > Integrations > ONVIF.",
            host,
            exc_info=True,
        )
