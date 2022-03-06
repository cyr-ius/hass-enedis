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
    CONF_PDL,
    COORDINATOR,
    DOMAIN,
    PLATFORMS,
    UNDO_LISTENER,
    CONF_PRODUCTION_DETAIL,
    CONF_PRODUCTION,
    CONF_CONSUMPTION_DETAIL,
)
from .enedisgateway import (
    EnedisException,
    EnedisGateway,
    LimitException,
    URL,
    MANUFACTURER,
)

CONFIG_SCHEMA = vol.Schema({vol.Optional(DOMAIN): {}}, extra=vol.ALLOW_EXTRA)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Enedis integration."""
    return True


async def async_setup_entry(hass, config_entry):
    """Set up Enedis as config entry."""
    hass.data.setdefault(DOMAIN, {})
    pdl = config_entry.data.get(CONF_PDL)
    session = async_create_clientsession(hass)

    """Collect data in database."""
    collector = EnedisDataInsertDBCoordinator(hass, config_entry, session)
    await collector.async_refresh()

    informations = {}
    try:
        informations.update(await collector.api.async_get_contracts())
        informations.update(await collector.api.async_get_addresses())
    except LimitException:
        pass
    except EnedisException as error:
        _LOGGER.error(error)
        return False

    coordinator = EnedisDataUpdateCoordinator(hass, config_entry, session)
    await coordinator.async_config_entry_first_refresh()

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
        model="9kVA",
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


class EnedisDataInsertDBCoordinator(DataUpdateCoordinator):
    """Define an object to fetch datas."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, session) -> None:
        """Class to manage fetching data API."""
        self.config = config_entry.data
        self.options = config_entry.options
        self.api = EnedisGateway(
            pdl=self.config[CONF_PDL], token=self.config[CONF_TOKEN], session=session
        )
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(hours=1))

    async def _async_update_data(self) -> dict:
        """Update database every hours."""
        try:
            await self.api.db.async_update()

            if self.options.get(CONF_CONSUMPTION_DETAIL):
                await self.api.db.async_update_detail()
            if self.options.get(CONF_PRODUCTION):
                await self.api.db.async_update(data_type="production")
            if self.options.get(CONF_PRODUCTION_DETAIL):
                await self.api.db.async_update_detail(data_type="production")

        except (EnedisException, LimitException) as error:
            raise UpdateFailed(error) from error
        return {}


class EnedisDataUpdateCoordinator(DataUpdateCoordinator):
    """Define an object to fetch datas."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, session) -> None:
        """Class to manage fetching data API."""
        self.config = config_entry.data
        self.api = EnedisGateway(
            pdl=self.config[CONF_PDL], token=self.config[CONF_TOKEN], session=session
        )
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(minutes=1)
        )

    async def _async_update_data(self) -> dict:
        try:
            datas = await self.api.db.async_get_sum(self.config[CONF_PDL])
            _LOGGER.debug(datas)
            return datas
        except EnedisException as error:
            raise UpdateFailed(error) from error
