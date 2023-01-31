"""Data Update Coordinator."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging

from myelectricaldatapy import EnedisByPDL, EnedisException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ACCESS,
    CONF_CONSUMPTION,
    CONF_CONTRACT,
    CONF_ECOWATT,
    CONF_PDL,
    CONF_PRICINGS,
    CONF_PRODUCTION,
    CONF_SERVICE,
    CONF_TEMPO,
    CONSUMPTION,
    CONSUMPTION_DAILY,
    CONSUMPTION_DETAIL,
    DOMAIN,
    PRODUCTION,
    PRODUCTION_DAILY,
    PRODUCTION_DETAIL,
    CONF_DATASET,
    CONF_RULES,
    CONF_AUTH,
)
from .helpers import async_fetch_datas, async_statistics, minus_date, rules_format

SCAN_INTERVAL = timedelta(hours=3)

_LOGGER = logging.getLogger(__name__)


class EnedisDataUpdateCoordinator(DataUpdateCoordinator):
    """Define an object to fetch datas."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Class to manage fetching data API."""
        self.last_access: datetime | None = None
        self.hass = hass
        self.entry = entry
        self.pdl: str = entry.data[CONF_PDL]
        token: str = (
            entry.options[CONF_AUTH][CONF_TOKEN]
            if entry.options.get(CONF_AUTH, {}).get(CONF_TOKEN)
            else entry.data[CONF_TOKEN]
        )
        self.api = EnedisByPDL(
            token=token, session=async_create_clientsession(hass), timeout=30
        )
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self) -> list(str, str):
        """Update data via API."""
        statistics = {}
        try:
            # Check  has a valid access
            statistics.update({ACCESS: await self.api.async_valid_access(self.pdl)})

            if self.last_access is None or self.last_access < datetime.now().date():
                # Get contract
                statistics.update(
                    {CONF_CONTRACT: await self.api.async_get_contract(self.pdl)}
                )
                # Get tempo day
                if (
                    self.entry.options.get(CONF_CONSUMPTION, {}).get(CONF_TEMPO)
                    and self.api.last_access
                ):
                    statistics.update({CONF_TEMPO: await self.api.async_get_tempoday()})
                # Get ecowatt information
                if self.entry.options.get(CONF_AUTH, {}).get(CONF_ECOWATT):
                    statistics.update(
                        {CONF_ECOWATT: await self.api.async_get_ecowatt()}
                    )
                self.last_access = datetime.now().date()
        except EnedisException as error:
            _LOGGER.error(error)

        try:
            # Add statistics in HA Database
            str_date = datetime.now().date().strftime("%Y-%m-%d")
            tempo_day = statistics.get(CONF_TEMPO, {}).get(str_date)

            for data in await self._async_datas_collect(tempo_day):
                _LOGGER.debug(data)
                stats = await async_statistics(self.hass, **data)
                statistics.update(stats)
        except EnedisException as error:
            _LOGGER.error(error)

        return statistics

    async def _async_datas_collect(self, tempo_day: str | None = None):
        """Prepare data."""
        datas_collected = []
        production = self.entry.options.get(CONF_PRODUCTION, {})
        consumption = self.entry.options.get(CONF_CONSUMPTION, {})
        if (service := production.get(CONF_SERVICE)) in [
            PRODUCTION_DAILY,
            PRODUCTION_DETAIL,
        ]:
            # Set rule
            rules = rules_format(
                self.pdl, PRODUCTION, production.get(CONF_PRICINGS, {})
            )

            start_date = (
                minus_date(365).date()
                if service in [PRODUCTION_DAILY]
                else minus_date(6).date()
            )
            end_date = datetime.now().date()

            # Fetch production datas
            dataset = await async_fetch_datas(
                self.api, self.pdl, service, start_date, end_date
            )
            datas_collected.append({CONF_DATASET: dataset, CONF_RULES: rules})

        if (service := consumption.get(CONF_SERVICE)) in [
            CONSUMPTION_DAILY,
            CONSUMPTION_DETAIL,
        ]:
            # Set rule
            rules = rules_format(
                self.pdl, CONSUMPTION, consumption.get(CONF_PRICINGS, {}), tempo_day
            )

            start_date = (
                minus_date(365).date()
                if service in [CONSUMPTION_DAILY]
                else minus_date(6).date()
            )
            end_date = datetime.now().date()
            # Fetch consumption datas
            dataset = await async_fetch_datas(
                self.api, self.pdl, service, start_date, end_date
            )
            datas_collected.append({CONF_DATASET: dataset, CONF_RULES: rules})

        return datas_collected
