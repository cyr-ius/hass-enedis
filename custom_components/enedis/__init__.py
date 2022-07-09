"""The Enedis integration."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import CONF_PDL, COORDINATOR, DOMAIN, PLATFORMS, RELOAD_HISTORY
from .enediscoordinator import EnedisDataUpdateCoordinator
from .enedisgateway import EnedisGateway

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Enedis as config entry."""
    hass.data.setdefault(DOMAIN, {})

    pdl = entry.data.get(CONF_PDL)
    token = entry.data.get(CONF_TOKEN)

    session = async_create_clientsession(hass)
    enedis = EnedisGateway(pdl=pdl, token=token, session=session)

    coordinator = EnedisDataUpdateCoordinator(hass, entry, enedis)
    await coordinator.async_config_entry_first_refresh()
    if coordinator.data is None:
        return False

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    hass.data[DOMAIN][entry.entry_id] = {COORDINATOR: coordinator, CONF_PDL: pdl}

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    async def async_reload_history(call) -> None:
        await coordinator.async_load_datas_history(call)

    hass.services.async_register(
        DOMAIN, RELOAD_HISTORY, async_reload_history, schema=vol.Schema({})
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
