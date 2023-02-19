"""Data Update Coordinator."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from myelectricaldatapy import EnedisAnalytics, EnedisByPDL, EnedisException

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN, ENERGY_KILO_WATT_HOUR
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_AUTH,
    CONF_CONSUMPTION,
    CONF_DATASET,
    CONF_ECOWATT,
    CONF_PDL,
    CONF_POWER_MODE,
    CONF_PRICING_COST,
    CONF_PRICING_INTERVALS,
    CONF_PRICING_NAME,
    CONF_PRODUCTION,
    CONF_RULE_END_TIME,
    CONF_RULE_START_TIME,
    CONF_SERVICE,
    CONF_TEMPO,
    CONSUMPTION_DAILY,
    CONSUMPTION_DETAIL,
    DOMAIN,
    PRODUCTION_DAILY,
    TEMPO_DAY,
)

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
        self.access: dict[str, Any] = {}
        self.contract: dict[str, Any] = {}
        self.access: dict[str, Any] = {}
        self.tempo: dict[str, Any] = {}
        self.tempo_day: dict[str, Any] = {}
        self.ecowatt: dict[str, Any] = {}
        self.ecowatt_day: str | None = None
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
        try:
            # Check  has a valid access
            self.access = await self.api.async_valid_access(self.pdl)

            if self.last_access is None or self.last_access < datetime.now().date():
                # Get contract
                self.contract = await self.api.async_get_contract(self.pdl)

                str_date = datetime.now().date().strftime("%Y-%m-%d")
                # Get tempo day
                if (
                    self.entry.options.get(CONF_CONSUMPTION, {}).get(CONF_TEMPO)
                    and self.api.last_access
                ):
                    self.tempo = await self.api.async_get_tempoday()
                    self.tempo_day = self.tempo.get(str_date, {})

                # Get ecowatt information
                if self.entry.options.get(CONF_AUTH, {}).get(CONF_ECOWATT):
                    self.ecowatt = await self.api.async_get_ecowatt()
                    self.ecowatt_day = self.ecowatt.get(str_date, {})

                self.last_access = datetime.now().date()
        except EnedisException as error:
            _LOGGER.error(error)

        # Fetch datas
        data_collected = await self._async_datas_collect(self.tempo_day)

        # Add statistics in HA Database
        statistics = {}
        try:
            for data in data_collected:
                _LOGGER.debug(data)
                stats = await async_statistics(self.hass, **data)
                statistics.update(stats)
        except EnedisException as error:
            _LOGGER.error("Update stats %s", error)

        return statistics

    async def _async_datas_collect(self, tempo_day: str | None = None):
        """Prepare data."""
        datas_collected = []
        production = self.entry.options.get(CONF_PRODUCTION, {})
        consumption = self.entry.options.get(CONF_CONSUMPTION, {})
        end_date = datetime.now().date()

        for option in [production, consumption]:
            service = option.get(CONF_SERVICE)

            start_date = (
                self.minus_date(365).date()
                if service in [PRODUCTION_DAILY, CONSUMPTION_DAILY]
                else self.minus_date(6).date()
            )

            power_mode = (
                CONF_CONSUMPTION
                if service in [CONSUMPTION_DAILY, CONSUMPTION_DETAIL]
                else CONF_PRODUCTION
            )

            # Fetch datas
            dataset = {}
            try:
                if service:
                    dataset = await self.api.async_fetch_datas(
                        service, self.pdl, start_date, end_date
                    )
            except EnedisException as error:
                _LOGGER.error("Fetch datas for %s (%s): %s", service, self.pdl, error)
            finally:
                dataset = dataset.get("meter_reading", {}).get("interval_reading", [])

            datas_collected.append(
                {
                    CONF_POWER_MODE: power_mode,
                    CONF_PDL: self.pdl,
                    TEMPO_DAY: tempo_day,
                    CONF_DATASET: dataset,
                    **option,
                }
            )

        return datas_collected

    def minus_date(self, days: int) -> datetime:
        """Substract now."""
        return datetime.now() - timedelta(days=days)


async def async_statistics(
    hass: HomeAssistant, dataset: dict, no_update: bool = False, **kwargs: Any
):
    """Compute statistics."""
    global_statistics = {}
    pricings = kwargs.get("pricings", {})
    tempo_day = kwargs.get(TEMPO_DAY)
    pdl = kwargs.get(CONF_PDL)
    power_mode = kwargs.get(CONF_POWER_MODE)

    for pricing in pricings.values():
        name = pricing[CONF_PRICING_NAME]
        statistic_id = f"{DOMAIN}:{pdl}_{power_mode}_{name}".lower()
        intervals = [
            (interval[CONF_RULE_START_TIME], interval[CONF_RULE_END_TIME])
            for interval in pricing[CONF_PRICING_INTERVALS].values()
        ]
        price = (
            pricing[tempo_day]
            if tempo_day and pricing.get(tempo_day)
            else pricing[CONF_PRICING_COST]
        )

        _LOGGER.debug("%s stat", statistic_id)

        # Fetch last information in database
        last_stats = await get_instance(hass).async_add_executor_job(
            get_last_statistics, hass, 1, statistic_id, True, "sum"
        )

        # Fetch last sum in database
        summary = 0 if not last_stats else last_stats[statistic_id][0]["sum"]

        # Fetch last time in database
        last_stats_time = (
            None
            if not last_stats
            else datetime.fromtimestamp(last_stats[statistic_id][0]["start"]).strftime(
                "%Y-%m-%d"
            )
        )
        _LOGGER.debug("Start date > %s", last_stats_time)

        analytics = EnedisAnalytics(dataset)
        datas_collected = analytics.get_data_analytcis(
            convertKwh=True,
            convertUTC=True,
            start_date=last_stats_time,
            intervals=intervals,
            groupby="date",
            freq="H",
            summary=True,
            cumsum=summary,
        )

        datas_collected = analytics.set_price(datas_collected, price, True)
        _LOGGER.debug(datas_collected)

        if sum_value := analytics.get_last_value(datas_collected, "date", "sum_value"):
            summary = sum_value

        if no_update is False:
            global_statistics.update({f"{power_mode} {name}".capitalize(): summary})

        stats = []
        costs = []
        for datas in datas_collected:
            stats.append(
                StatisticData(
                    start=datas["date"], state=datas["value"], sum=datas["sum_value"]
                )
            )
            costs.append(
                StatisticData(
                    start=datas["date"], state=datas["price"], sum=datas["sum_price"]
                )
            )

        if stats and costs:
            _LOGGER.debug("Add %s stat in table", name)
            metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=name,
                source=DOMAIN,
                statistic_id=statistic_id,
                unit_of_measurement=ENERGY_KILO_WATT_HOUR,
            )
            hass.async_add_executor_job(
                async_add_external_statistics, hass, metadata, stats
            )
            _LOGGER.debug("Add %s cost in table", name)
            metacost = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=f"{name}_cost",
                source=DOMAIN,
                statistic_id=f"{statistic_id}_cost",
                unit_of_measurement="EUR",
            )
            hass.async_add_executor_job(
                async_add_external_statistics, hass, metacost, costs
            )

    return global_statistics
