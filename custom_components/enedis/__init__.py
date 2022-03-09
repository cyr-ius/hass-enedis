"""The Enedis integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

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
from .enedisgateway import MANUFACTURER, URL, EnedisException, EnedisGateway

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
    db = hass.config.path("enedis-gateway.db")

    coordinator = EnedisDataUpdateCoordinator(hass, config_entry, session, db)
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

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, session, db
    ) -> None:
        """Class to manage fetching data API."""
        self.config = config_entry.data
        self.options = config_entry.options
        self.api = EnedisGateway(
            pdl=self.config[CONF_PDL],
            token=self.config[CONF_TOKEN],
            session=session,
            db=db,
        )
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(hours=1))

    async def _async_update_data(self) -> dict:
        """Update database every hours."""
        start = (datetime.now() + timedelta(days=-7)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
        try:
            contracts = await self.api.async_get_contract_by_pdl()
            fetch_datas = {"contracts": contracts}

            if self.options.get(CONF_CONSUMPTION, True):
                consumption = await self.api.async_get_sum(
                    service="consumption", start=start, end=end
                )
                fetch_datas.update({CONF_CONSUMPTION: consumption})

            if self.options.get(CONF_CONSUMPTION_DETAIL):
                consumption_detail = await self.api.async_get_detail(
                    service="consumption", start=start, end=end
                )
                fetch_datas.update({CONF_CONSUMPTION_DETAIL: consumption_detail})

            if self.options.get(CONF_PRODUCTION):
                production = await self.api.async_get_sum(
                    service="production", start=start, end=end
                )
                fetch_datas.update({CONF_PRODUCTION: production})

            if self.options.get(CONF_PRODUCTION_DETAIL):
                production_detail = await self.api.async_get_detail(
                    service="production", start=start, end=end
                )
                fetch_datas.update({CONF_PRODUCTION_DETAIL: production_detail})

        except EnedisException as error:
            raise UpdateFailed(error) from error

        _LOGGER.debug(fetch_datas)
        return fetch_datas
