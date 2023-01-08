"""Data Update Coordinator."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from myelectricaldatapy import EnedisByPDL, EnedisException
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_AFTER, CONF_BEFORE, CONF_NAME, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ACCESS,
    TEMPO,
    CONF_CONSUMTPION,
    CONF_PDL,
    CONF_PRODUCTION,
    CONF_QUERY,
    CONF_RULE_END_TIME,
    CONF_RULE_NAME,
    CONF_RULE_PRICE,
    CONF_RULE_START_TIME,
    CONF_RULES,
    CONF_STATISTIC_ID,
    CONSUMPTION,
    CONSUMPTION_DAILY,
    CONSUMPTION_DETAIL,
    CONTRACTS,
    COST_CONSUMTPION,
    COST_PRODUCTION,
    DOMAIN,
    PRODUCTION,
    PRODUCTION_DAILY,
    PRODUCTION_DETAIL,
)
from .helpers import async_fetch_datas, datetostr

SCAN_INTERVAL = timedelta(hours=3)

_LOGGER = logging.getLogger(__name__)


class EnedisDataUpdateCoordinator(DataUpdateCoordinator):
    """Define an object to fetch datas."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Class to manage fetching data API."""
        self.hass = hass
        self.entry = entry
        self.pdl = entry.data[CONF_PDL]
        token = (
            entry.options[CONF_TOKEN]
            if entry.options.get(CONF_TOKEN)
            else entry.data[CONF_TOKEN]
        )
        self.api = EnedisByPDL(
            token=token,
            session=async_create_clientsession(hass),
            timeout=30,
        )
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self) -> list(str, str):
        """Update data via API."""
        statistics = {}
        tempo_day = None

        try:
            access = await self.api.async_fetch_datas("valid_access", self.pdl)
            statistics.update({ACCESS: access})

            if not (contracts := statistics.get("contracts", {})):
                # Fetch contract datas
                contracts = await self.api.async_get_contract(self.pdl)
                statistics.update({CONTRACTS: contracts})

            if datetostr(datetime.now()) != tempo_day:
                # Fetch tempo datas
                tempo_day = datetostr(datetime.now())
                tempo = await self.api.async_fetch_datas(
                    f"rte/tempo/{tempo_day}/{tempo_day}", ""
                )
                statistics.update({TEMPO: tempo.get(tempo_day)})
        except EnedisException as error:
            _LOGGER.error(error)

        # Fetch consumption and production datas
        rules = self.entry.options.get(CONF_RULES, {})
        if self.entry.options.get(CONF_PRODUCTION) in [
            PRODUCTION_DAILY,
            PRODUCTION_DETAIL,
        ]:
            mode = {
                CONF_QUERY: self.entry.options.get(CONF_PRODUCTION),
                CONF_AFTER: self.minus_date(365)
                if self.entry.options.get(CONF_PRODUCTION) in [PRODUCTION_DAILY]
                else self.minus_date(6),
                CONF_BEFORE: datetime.now(),
                CONF_RULES: [
                    {
                        CONF_NAME: PRODUCTION.lower(),
                        CONF_STATISTIC_ID: f"{DOMAIN}:{self.pdl}_{PRODUCTION}".lower(),
                        CONF_RULE_NAME: None,
                        CONF_RULE_START_TIME: "00:00:00",
                        CONF_RULE_END_TIME: "00:00:00",
                        CONF_RULE_PRICE: self.entry.options.get(COST_PRODUCTION),
                    },
                ],
                CONF_PDL: self.pdl,
            }
            datas = await async_fetch_datas(self.hass, self.api, **mode)
            statistics.update(datas)

        if self.entry.options.get(CONF_CONSUMTPION) in [CONSUMPTION_DAILY] or (
            self.entry.options.get(CONF_CONSUMTPION) in [CONSUMPTION_DETAIL]
            and len(rules.keys()) == 0
        ):
            mode = {
                CONF_QUERY: self.entry.options.get(CONF_CONSUMTPION),
                CONF_AFTER: self.minus_date(365)
                if self.entry.options.get(CONF_CONSUMTPION) in [CONSUMPTION_DAILY]
                else self.minus_date(6),
                CONF_BEFORE: datetime.now(),
                CONF_RULES: [
                    {
                        CONF_NAME: CONSUMPTION.lower(),
                        CONF_STATISTIC_ID: f"{DOMAIN}:{self.pdl}_{CONSUMPTION}".lower(),
                        CONF_RULE_NAME: None,
                        CONF_RULE_START_TIME: "00:00:00",
                        CONF_RULE_END_TIME: "00:00:00",
                        CONF_RULE_PRICE: self.entry.options.get(COST_CONSUMTPION),
                    },
                ],
                CONF_PDL: self.pdl,
            }
            datas = await async_fetch_datas(self.hass, self.api, **mode)
            statistics.update(datas)
        elif (
            self.entry.options.get(CONF_CONSUMTPION) in [CONSUMPTION_DETAIL]
            and len(rules.keys()) > 0
        ):
            datas_rules = []
            for rule in rules.values():
                datas_rules.append(
                    {
                        CONF_NAME: f"{CONSUMPTION}_{rule[CONF_RULE_NAME]}".lower(),
                        CONF_STATISTIC_ID: f"{DOMAIN}:{self.pdl}_{CONSUMPTION}_{rule[CONF_RULE_NAME]}".lower(),
                        CONF_RULE_NAME: rule[CONF_RULE_NAME],
                        CONF_RULE_START_TIME: rule[CONF_RULE_START_TIME],
                        CONF_RULE_END_TIME: rule[CONF_RULE_END_TIME],
                        CONF_RULE_PRICE: rule[CONF_RULE_PRICE],
                    }
                )

            mode = {
                CONF_QUERY: self.entry.options.get(CONF_CONSUMTPION),
                CONF_AFTER: self.minus_date(6),
                CONF_BEFORE: datetime.now(),
                CONF_RULES: datas_rules,
                CONF_PDL: self.pdl,
            }
            datas = await async_fetch_datas(self.hass, self.api, **mode)
            statistics.update(datas)

        return statistics

    @staticmethod
    def minus_date(days: int) -> datetime:
        """Substract now."""
        return datetime.now() - timedelta(days=days)
