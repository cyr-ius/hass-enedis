"""Data Update Coordinator."""
from __future__ import annotations
import re
import logging
from datetime import datetime, timedelta

import voluptuous as vol
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ENERGY_KILO_WATT_HOUR, CONF_SOURCE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_DETAIL, CONF_PDL, DOMAIN
from .enedisgateway import HC, HP, EnedisException

CONFIG_SCHEMA = vol.Schema({vol.Optional(DOMAIN): {}}, extra=vol.ALLOW_EXTRA)
SCAN_INTERVAL = timedelta(hours=2)

_LOGGER = logging.getLogger(__name__)


class EnedisDataUpdateCoordinator(DataUpdateCoordinator):
    """Define an object to fetch datas."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, api) -> None:
        """Class to manage fetching data API."""
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.hass = hass
        self.pdl = config_entry.data[CONF_PDL]
        self.power = config_entry.options[CONF_SOURCE].lower()
        self.hp = config_entry.options.get(HP)
        self.hc = config_entry.options.get(HC)
        self.detail = config_entry.options.get(CONF_DETAIL, False)
        self.enedis = api
        self.statistics = {}

    async def _async_update_data(self):
        """Update data via API."""
        unit = ENERGY_KILO_WATT_HOUR
        start = (
            (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
            if self.detail
            else (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        )
        end = datetime.now().strftime("%Y-%m-%d")

        if (contracts := self.statistics.get("contracts", {})) is None or len(
            contracts
        ) == 0:
            try:
                contracts = await self.enedis.async_get_contract_by_pdl()
            except EnedisException:
                _LOGGER.warning("Contract data is not complete")

        try:
            datas = await self.enedis.async_get_datas(
                self.power, start, end, self.detail
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
        last_stats =  await get_instance(self.hass).async_add_executor_job(
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

    async def _async_offpeak_statistics(self, hourly_data, unit) -> dict:
        if self.detail is False:
            _LOGGER.debug("Off-peak hours are not eligible")
            return
        statistic_id = f"{DOMAIN}:{self.pdl}_{self.power}_offpeak"
        last_stats = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics, self.hass, 1, statistic_id, True
        )

        if not last_stats:
            energy_sum = 0
            last_stats_time = None
        else:
            energy_sum = last_stats[statistic_id][0]["sum"]
            last_stats_time = dt_util.parse_datetime(
                last_stats[statistic_id][0]["start"]
            )
        _LOGGER.debug(f"Last date in database  {last_stats_time}")

        statistics = []
        statistics_cost = []
        ref_date = None
        last_value = 0
        for data in hourly_data:
            if (value := int(data.get("value"))) is None:
                continue

            start = dt_util.parse_datetime(data["date"]).replace(tzinfo=dt_util.UTC)
            if last_stats_time is not None and start <= last_stats_time + timedelta(
                days=1
            ):
                continue

            if start.time() > datetime.min.time():
                if self.enedis.check_offpeak(start):
                    if ref_date is None:
                        ref_date = datetime.combine(
                            start.date(), datetime.min.time()
                        ).replace(tzinfo=dt_util.UTC)
                    interval = float(
                        self.weighted_interval(data.get("interval_length"))
                    )
                    _LOGGER.debug(
                        f"Offpeak Value {value} - Interval {interval} Hours {start}"
                    )
                    last_value += value * interval
                continue
            else:
                if last_value > 0:

                    if self.enedis.check_offpeak(start):
                        interval = float(
                            self.weighted_interval(data.get("interval_length"))
                        )
                        last_value += value * interval
                        _LOGGER.debug(
                            f"Offpeak Value {value} - Interval {interval} Hours {start}"
                        )

                    value_kwh = round(last_value / 1000, 2)
                    statistics_cost.append((ref_date, value_kwh))
                    energy_sum += value_kwh

                    _LOGGER.debug(
                        f"Offpeak Hours: {value_kwh} at {ref_date}, sum is {round(energy_sum, 2)}"
                    )
                    statistics.append(
                        StatisticData(
                            start=ref_date, state=value_kwh, sum=round(energy_sum, 2)
                        )
                    )
                    last_value = 0
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

        if self.hc:
            await self._async_insert_costs(
                statistics_cost,
                f"{DOMAIN}:{self.pdl}_{self.power}_offpeak_cost",
                f"Price of off-peak hours {self.power} ({self.pdl})",
                self.hc,
            )

        return energy_sum

    async def _async_peak_statistics(
        self, hourly_data, unit, force=False, statistic_id=None
    ) -> dict:
        if statistic_id is None:
            statistic_id = f"{DOMAIN}:{self.pdl}_{self.power}_peak"
        last_stats = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics, self.hass, 1, statistic_id, True
        )

        if not last_stats or force is True:
            energy_sum = 0
            last_stats_time = None
        else:
            energy_sum = last_stats[statistic_id][0]["sum"]
            last_stats_time = dt_util.parse_datetime(
                last_stats[statistic_id][0]["start"]
            )
        _LOGGER.debug(f"Last date in database  {last_stats_time}")

        statistics = []
        statistics_cost = []
        last_value = 0
        ref_date = None
        for data in hourly_data:
            if (value := int(data.get("value"))) is None:
                continue

            start = dt_util.parse_datetime(data["date"]).replace(tzinfo=dt_util.UTC)
            if last_stats_time is not None and start <= last_stats_time + timedelta(
                days=1
            ):
                continue

            if start.time() > datetime.min.time():
                if not self.enedis.check_offpeak(start):
                    if ref_date is None:
                        ref_date = datetime.combine(
                            start.date(), datetime.min.time()
                        ).replace(tzinfo=dt_util.UTC)
                    interval = float(
                        self.weighted_interval(data.get("interval_length"))
                    )
                    _LOGGER.debug(
                        f"Peak Value {value} - Interval {interval} Hours {start}"
                    )
                    last_value += value * interval
                continue
            else:
                date_refer = value_kwh = None
                if last_value > 0:

                    if not self.enedis.check_offpeak(start):
                        interval = float(
                            self.weighted_interval(data.get("interval_length"))
                        )
                        last_value += value * interval

                        _LOGGER.debug(
                            f"Peak Value {value} - Interval {interval} Hours {start}"
                        )

                    value_kwh = round(last_value / 1000, 2)
                    date_refer = ref_date
                    last_value = 0
                    ref_date = None
                else:
                    value_kwh = round(value / 1000, 2)
                    date_refer = start

                statistics_cost.append((date_refer, value_kwh))
                energy_sum += value_kwh
                _LOGGER.debug(
                    f"Peak Hours : {value_kwh} at {date_refer}, sum is {round(energy_sum, 2)}"
                )
                statistics.append(
                    StatisticData(
                        start=date_refer, state=value_kwh, sum=round(energy_sum, 2)
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

        if self.hp and force is False:
            await self._async_insert_costs(
                statistics_cost,
                f"{DOMAIN}:{self.pdl}_{self.power}_peak_cost",
                f"Price of peak hours {self.power} ({self.pdl})",
                self.hp,
            )

        return energy_sum

    def weighted_interval(self, interval):
        """Compute weighted."""
        if interval is None:
            return 1
        rslt = re.findall("PT([0-9]{2})M", interval)
        if len(rslt) == 1:
            return int(rslt[0]) / 60

    async def async_load_datas_history(self, call):
        """Load datas in statics table."""
        unit = ENERGY_KILO_WATT_HOUR
        statistic_id = f"{DOMAIN}:{self.pdl}_{self.power}_peak"
        start = (datetime.now() - timedelta(days=365)).replace(tzinfo=dt_util.UTC)

        stat = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            start,
            None,
            [statistic_id],
            "hour",
            True,
        )
        start = start.strftime("%Y-%m-%d")
        end = (stat[statistic_id][0]["start"].date() - timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
        statistic_id = f"{DOMAIN}:{self.pdl}_{self.power}"

        try:
            datas = await self.enedis.async_get_datas(
                self.power, start, end, self.detail
            )
            hourly_data = datas.get("meter_reading", {}).get("interval_reading", [])
        except EnedisException:
            hourly_data = []

        await self._async_peak_statistics(hourly_data, unit, True, statistic_id)
