"""The Enedis integration."""
from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_AFTER, CONF_BEFORE
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    CONF_POWER_MODE,
    CONF_STATISTIC_ID,
    DOMAIN,
    PLATFORMS,
    FETCH_SERVICE,
    CLEAR_SERVICE,
    CONF_RULES,
    CONF_RULE_START_TIME,
    CONF_RULE_END_TIME,
    CONF_ENTRY,
)
from .coordinator import EnedisDataUpdateCoordinator
from .helpers import async_service_load_datas_history, async_service_datas_clear

_LOGGER = logging.getLogger(__name__)

HISTORY_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY): str,
        vol.Optional(CONF_POWER_MODE): str,
        vol.Optional(CONF_AFTER): cv.date,
        vol.Optional(CONF_BEFORE): cv.date,
    }
)
CLEAR_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_STATISTIC_ID): str,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Enedis as config entry."""
    hass.data.setdefault(DOMAIN, {})

    if (
        entry.options.get("peak_cost") is not None
        and entry.options.get("offpeak_cost") is not None
    ):
        options = dict(entry.options).copy()
        for k, rule in entry.options.get(CONF_RULES).items():
            rule[
                CONF_RULE_START_TIME
            ] = f'{rule[CONF_RULE_START_TIME].replace("H", ":")}:00'
            rule[
                CONF_RULE_END_TIME
            ] = f'{rule[CONF_RULE_END_TIME].replace("H", ":")}:00'
        options[CONF_RULES] = entry.options.get(CONF_RULES)
        options.pop("peak_cost")
        options.pop("offpeak_cost")
        hass.config_entries.async_update_entry(entry=entry, options=options)

    coordinator = EnedisDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_reload_history(call: ServiceCall) -> None:
        await async_service_load_datas_history(hass, coordinator.api, call)

    async def async_clear(call: ServiceCall) -> None:
        await async_service_datas_clear(hass, call)

    hass.services.async_register(
        DOMAIN, FETCH_SERVICE, async_reload_history, schema=HISTORY_SERVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, CLEAR_SERVICE, async_clear, schema=CLEAR_SERVICE_SCHEMA
    )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
