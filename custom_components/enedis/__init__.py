"""The Enedis integration."""
from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import CONF_PDL, COORDINATOR, DOMAIN, PLATFORMS, UNDO_LISTENER
from .enedisgateway import EnedisGateway
from .enediscoordinator import EnedisDataUpdateCoordinator

CONFIG_SCHEMA = vol.Schema({vol.Optional(DOMAIN): {}}, extra=vol.ALLOW_EXTRA)
SCAN_INTERVAL = timedelta(hours=2)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Enedis integration."""
    return True


async def async_setup_entry(hass, config_entry):
    """Set up Enedis as config entry."""
    hass.data.setdefault(DOMAIN, {})
    pdl = config_entry.data.get(CONF_PDL)
    token = config_entry.data.get(CONF_TOKEN)
    session = async_create_clientsession(hass)

    enedis = EnedisGateway(pdl=pdl, token=token, session=session)

    coordinator = EnedisDataUpdateCoordinator(hass, config_entry, enedis)
    await coordinator.async_config_entry_first_refresh()

    if coordinator.data is None:
        return False

    undo_listener = config_entry.add_update_listener(_async_update_listener)

    hass.data[DOMAIN][config_entry.entry_id] = {
        COORDINATOR: coordinator,
        CONF_PDL: pdl,
        UNDO_LISTENER: undo_listener,
    }

    hass.config_entries.async_setup_platforms(config_entry, PLATFORMS)

    async def async_reload_history(call) -> None:
        await coordinator.async_load_datas_history(call)

    hass.services.async_register(
        DOMAIN, "reload_history", async_reload_history, schema=vol.Schema({})
    )

    return True


async def async_unload_entry(hass, config_entry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    if unload_ok:
        hass.data[DOMAIN][config_entry.entry_id][UNDO_LISTENER]()
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
