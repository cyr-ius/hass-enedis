"""The Enedis integration."""
from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_AFTER, CONF_BEFORE, CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from .const import CONF_POWER_MODE, DOMAIN, PLATFORMS, RELOAD_HISTORY
from .coordinator import EnedisDataUpdateCoordinator
from .helpers import async_service_load_datas_history

_LOGGER = logging.getLogger(__name__)

HISTORY_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DEVICE_ID): str,
        vol.Optional(CONF_POWER_MODE): str,
        vol.Optional(CONF_AFTER): cv.date,
        vol.Optional(CONF_BEFORE): cv.date,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Enedis as config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = EnedisDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_reload_history(call: ServiceCall) -> None:
        await async_service_load_datas_history(hass, coordinator.enedis, call)

    hass.services.async_register(
        DOMAIN, RELOAD_HISTORY, async_reload_history, schema=HISTORY_SERVICE_SCHEMA
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
