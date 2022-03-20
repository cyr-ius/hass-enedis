"""Data Update Coordinator."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import voluptuous as vol
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ENERGY_KILO_WATT_HOUR, CONF_SOURCE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_DETAIL, CONF_PDL, DOMAIN
from .enedisgateway import HC, HP, EnedisException

CONFIG_SCHEMA = vol.Schema({vol.Optional(DOMAIN): {}}, extra=vol.ALLOW_EXTRA)
SCAN_INTERVAL = timedelta(hours=1)

_LOGGER = logging.getLogger(__name__)


class EnedisDataUpdateCoordinator(DataUpdateCoordinator):
    """Define an object to fetch datas."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, api) -> None:
        """Class to manage fetching data API."""
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.hass = hass
        self.pdl = config_entry.data[CONF_PDL]
        self.power = config_entry.options[CONF_SOURCE].lower()
        self.hp = config_entry.options[HP]
        self.hc = config_entry.options.get(HC)
        self.detail = config_entry.options.get(CONF_DETAIL, False)
        self.start = (
            (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
            if self.detail
            else (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        )
        self.end = datetime.now().strftime("%Y-%m-%d")
        self.enedis = api
        self.statistics = {}

    async def _async_update_data(self):
        """Update data via API."""
        unit = ENERGY_KILO_WATT_HOUR
        if (contracts := self.statistics.get("contracts", {})) is None or len(
            contracts
        ) == 0:
            try:
                _LOGGER.debug("fetch contracts information")
                contracts = await self.enedis.async_get_contract_by_pdl()
            except EnedisException:
                _LOGGER.warning("Contract data is not complete")

        try:
            datas = await self.enedis.async_get_datas(
                self.power, self.start, self.end, self.detail
            )
            hourly_data = datas.get("meter_reading", {}).get("interval_reading", [])
        except EnedisException:
            hourly_data = []

        try:
            offpeak_hours = await self._async_offpeak_statistics(hourly_data, unit)
            peak_hours = await self._async_peak_statistics(hourly_data, unit)
            self.statistics = {
                "contracts": contracts,
                "energy": {
                    CONF_SOURCE: self.power,
                    "offpeak_hours": offpeak_hours,
                    "peak_hours": peak_hours,
                },
            }
        except EnedisException as error:
            raise UpdateFailed(error)

        return self.statistics

    async def _async_insert_costs(self, statistics, statistic_id, name, price) -> dict:
        """Insert costs."""
        last_stats = await self.hass.async_add_executor_job(
            get_last_statistics, self.hass, 1, statistic_id, True
        )
        cost_sum = 0 if not last_stats else last_stats[statistic_id][0]["sum"]

        costs = []
        for stat in statistics:
            _cost = round(stat[1] * price, 2)
            cost_sum += _cost
            costs.append(StatisticData(start=stat[0], state=_cost, sum=cost_sum))

        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=name,
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_of_measurement="EUR",
        )
        async_add_external_statistics(self.hass, metadata, costs)

    def _offpeak_costs(self, start):
        """Compute cost for offpeak hour."""
        start_time = start.time()
        if self.enedis.has_offpeak:
            for range in self.enedis.get_offpeak():
                starting = datetime.strptime(range[0], "%HH%M").time()
                ending = datetime.strptime(range[1], "%HH%M").time()
                if start_time > starting and start_time <= ending:
                    return True
        return False

    async def _async_offpeak_statistics(self, hourly_data, unit) -> dict:
        if self.detail is False:
            return
        statistic_id = f"{DOMAIN}:{self.pdl}_{self.power}_offpeak"
        last_stats = await self.hass.async_add_executor_job(
            get_last_statistics, self.hass, 1, statistic_id, True
        )

        if not last_stats:
            _sum = 0
            last_stats_time = None
        else:
            _sum = last_stats[statistic_id][0]["sum"]
            last_stats_time = dt_util.parse_datetime(
                last_stats[statistic_id][0]["start"]
            )

        _LOGGER.debug(f"Valeur déjà en base {last_stats_time}")

        statistics = []
        val_memory = i = 0
        ref_date = None
        _costs = []

        for data in hourly_data:
            i += 1

            if (value := int(data.get("value"))) is None:
                continue

            start = dt_util.parse_datetime(data["date"]).replace(tzinfo=dt_util.UTC)

            if last_stats_time is not None and start <= last_stats_time + timedelta(
                days=1
            ):
                continue

            if start.time() > datetime.min.time():
                if self._offpeak_costs(start):
                    if ref_date is None:
                        ref_date = datetime.combine(
                            start.date(), datetime.min.time()
                        ).replace(tzinfo=dt_util.UTC)
                    val_memory += value * 0.5
                continue
            else:
                if val_memory > 0:
                    _costs.append((ref_date, round(val_memory / 1000, 2)))
                    _sum += val_memory

                    _LOGGER.debug(
                        f"Offpeak Hours : {round(val_memory / 1000, 2)} at {ref_date} - sum is {round(_sum / 1000, 2)}"
                    )
                    statistics.append(
                        StatisticData(
                            start=ref_date,
                            state=round(val_memory / 1000, 2),
                            sum=round(_sum / 1000, 2),
                        )
                    )
                    val_memory = 0
                    ref_date = None

        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=f"Off-peak {self.power} ({self.pdl})",
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_of_measurement=unit,
        )

        async_add_external_statistics(self.hass, metadata, statistics)

        await self._async_insert_costs(
            _costs,
            f"{DOMAIN}:{self.pdl}_{self.power}_offpeak_cost",
            f"Off-Peak Hours {self.power} ({self.pdl})",
            self.hc,
        )

        return _sum

    async def _async_peak_statistics(self, hourly_data, unit) -> dict:
        statistic_id = f"{DOMAIN}:{self.pdl}_{self.power}_peak"
        last_stats = await self.hass.async_add_executor_job(
            get_last_statistics, self.hass, 1, statistic_id, True
        )

        if not last_stats:
            _sum = 0
            last_stats_time = None
        else:
            _sum = last_stats[statistic_id][0]["sum"]
            last_stats_time = dt_util.parse_datetime(
                last_stats[statistic_id][0]["start"]
            )

        _LOGGER.debug(f"Valeur déjà en base {last_stats_time}")

        statistics = []
        val_memory = i = 0
        ref_date = None
        _costs = []

        for data in hourly_data:
            i += 1

            if (value := int(data.get("value"))) is None:
                continue

            start = dt_util.parse_datetime(data["date"]).replace(tzinfo=dt_util.UTC)

            if last_stats_time is not None and start <= last_stats_time + timedelta(
                days=1
            ):
                continue

            if start.time() > datetime.min.time():
                if not self._offpeak_costs(start):
                    if ref_date is None:
                        ref_date = datetime.combine(
                            start.date(), datetime.min.time()
                        ).replace(tzinfo=dt_util.UTC)
                    val_memory += value * 0.5
                continue
            else:
                if val_memory > 0:
                    _costs.append((ref_date, round(val_memory / 1000, 2)))
                    _sum += val_memory

                    _LOGGER.debug(
                        f"Peak Hours : {round(val_memory / 1000, 2)} at {ref_date} - sum is {round(_sum / 1000, 2)}"
                    )
                    statistics.append(
                        StatisticData(
                            start=ref_date,
                            state=round(val_memory / 1000, 2),
                            sum=round(_sum / 1000, 2),
                        )
                    )
                    val_memory = 0
                    ref_date = None
                else:
                    _costs.append((start, round(value / 1000, 2)))
                    _sum += value
                    _LOGGER.debug(
                        f"Peak Hours : {round(value / 1000, 2)} at {start} - sum is {round(_sum / 1000, 2)}"
                    )
                    statistics.append(
                        StatisticData(
                            start=start,
                            state=round(value / 1000, 2),
                            sum=round(_sum / 1000, 2),
                        )
                    )

        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=f"Peak {self.power} ({self.pdl})",
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_of_measurement=unit,
        )

        async_add_external_statistics(self.hass, metadata, statistics)

        await self._async_insert_costs(
            _costs,
            f"{DOMAIN}:{self.pdl}_{self.power}_peak_cost",
            f"Peak Hours {self.power} ({self.pdl})",
            self.hp,
        )

        return _sum
