"""The Enedis integration."""
from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CONSUMPTION,
    CONF_CONSUMPTION_DETAIL,
    CONF_PDL,
    CONF_PRODUCTION,
    CONF_PRODUCTION_DETAIL,
    COORDINATOR,
    DOMAIN,
    PLATFORMS,
    UNDO_LISTENER,
)
from .enedisgateway import MANUFACTURER, URL, EnedisException, Enedis

CONFIG_SCHEMA = vol.Schema({vol.Optional(DOMAIN): {}}, extra=vol.ALLOW_EXTRA)
SCAN_INTERVAL = timedelta(hours=1)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Enedis integration."""
    return True


async def async_setup_entry(hass, config_entry):
    """Set up Enedis as config entry."""
    hass.data.setdefault(DOMAIN, {})
    pdl = config_entry.data.get(CONF_PDL)

    coordinator = EnedisDataUpdateCoordinator(hass, config_entry)
    await coordinator.async_config_entry_first_refresh()

    if coordinator.data is None:
        return False

    undo_listener = config_entry.add_update_listener(_async_update_listener)

    hass.data[DOMAIN][config_entry.entry_id] = {
        COORDINATOR: coordinator,
        CONF_PDL: pdl,
        UNDO_LISTENER: undo_listener,
    }

    device_registry = await dr.async_get_registry(hass)
    device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, pdl)},
        name=f"Linky ({pdl})",
        configuration_url=URL,
        manufacturer=MANUFACTURER,
        model=coordinator.data["contracts"].get("subscribed_power"),
        suggested_area="Garage",
    )

    hass.config_entries.async_setup_platforms(config_entry, PLATFORMS)

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


class EnedisDataUpdateCoordinator(DataUpdateCoordinator):
    """Define an object to fetch datas."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Class to manage fetching data API."""
        self.session = async_create_clientsession(hass)
        self.config = config_entry.data
        self.options = config_entry.options
        self.pdl = self.config[CONF_PDL]
        self.enedis = Enedis(
            pdl=self.config[CONF_PDL],
            token=self.config[CONF_TOKEN],
            db=hass.config.path("enedis-gateway.db"),
            session=self.session,
        )
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self) -> dict:
        """Update and fetch datas."""
        try:
            consumption = self.options.get(CONF_CONSUMPTION, True)
            consumption_detail = self.options.get(CONF_CONSUMPTION_DETAIL, False)

            production = self.options.get(CONF_PRODUCTION, False)
            production_detail = self.options.get(CONF_PRODUCTION_DETAIL, False)

            return await self.enedis.async_update(
                (consumption, consumption_detail),
                (production, production_detail),
            )

        except EnedisException as error:
            raise UpdateFailed(error) from error
