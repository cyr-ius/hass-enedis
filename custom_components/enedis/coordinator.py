"""Data Update Coordinator."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from enedisgatewaypy import EnedisByPDL, EnedisException
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_TOKEN,
    ENERGY_KILO_WATT_HOUR,
    CONF_DEVICE_ID,
    CONF_AFTER,
    CONF_BEFORE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CC,
    CONF_CONSUMTPION,
    CONF_PDL,
    CONF_POWER_MODE,
    CONF_PRODUCTION,
    CONF_RULE_END_TIME,
    CONF_RULE_NAME,
    CONF_RULE_PRICE,
    CONF_RULE_START_TIME,
    CONF_RULES,
    CONSUMPTION,
    CONSUMPTION_DAILY,
    CONSUMPTION_DETAIL,
    CONTRACTS,
    DOMAIN,
    PC,
    PRODUCTION,
    PRODUCTION_DAILY,
    PRODUCTION_DETAIL,
    TEST_VALUES,
)

SCAN_INTERVAL = timedelta(hours=3)

_LOGGER = logging.getLogger(__name__)


class EnedisDataUpdateCoordinator(DataUpdateCoordinator):
    """Define an object to fetch datas."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Class to manage fetching data API."""
        self.hass = hass
        self.pdl = entry.data[CONF_PDL]
        self.options = entry.options
        self.modes = self.get_mode(entry)

        self.enedis = EnedisByPDL(
            pdl=self.pdl,
            token=entry.data[CONF_TOKEN],
            session=async_create_clientsession(hass),
            timeout=30,
        )
        self.statistics = {}
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self) -> list(str, str):
        """Update data via API."""
        # Fetch contract datas
        if not (contracts := self.statistics.get("contracts", {})):
            try:
                # contracts = await self.enedis.async_get_contract()
                self.statistics.update({CONTRACTS: contracts})
            except EnedisException as error:
                _LOGGER.error(error)

        # Fetch consumption and production datas
        for mode in self.modes:
            datas = await self._async_fetch_datas(**mode)
            self.statistics.update(datas)
        return self.statistics

    async def _async_fetch_datas(
        self, query: str, rules: list(str, str), start: datetime, end: datetime
    ) -> dict:
        """Fetch datas."""
        try:
            # Collect interval
            datas = await self.enedis.async_fetch_datas(query, start, end)
            datas_collected = datas.get("meter_reading", {}).get("interval_reading", [])
            # datas_collected = TEST_VALUES
            return await self._async_statistics(datas_collected, rules)
        except EnedisException as error:
            _LOGGER.error(error)

    async def _async_statistics(
        self, datas_collected: list(str, str), rules: list = None
    ):
        """Compute statistics."""
        global_statistics = {}
        collects = {}
        for rule in rules:
            statistic_id = rule["statistic_id"]
            price_interval = rule["price_interval"]
            name = rule["name"]

            if collects.get(name) is None:
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=name,
                    source=DOMAIN,
                    statistic_id=statistic_id,
                    unit_of_measurement=ENERGY_KILO_WATT_HOUR,
                )
                collects.update(
                    {
                        name: {
                            "metadata": metadata,
                            "statistics": {},
                            "price": price_interval[3],
                            "statistic_id": statistic_id,
                        }
                    }
                )

            # Fetch last information in database
            last_stats = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 1, statistic_id, True
            )

            # Fetch last sum in database
            summary = 0 if not last_stats else last_stats[statistic_id][0]["sum"]

            # Fetch last time in database
            last_stats_time = (
                None
                if not last_stats
                else dt_util.parse_datetime(last_stats[statistic_id][0]["start"])
            )

            _LOGGER.debug(f"Last date in database  {last_stats_time}")
            ref_date = None
            value = 0
            for data in datas_collected:
                if (value_collected := int(data.get("value"))) is None:
                    continue

                interval = float(self.weighted_interval(data.get("interval_length")))
                value_collected = value_collected / 1000 * interval  # Convert Wh to Kwh

                date_collected = dt_util.parse_datetime(data["date"]).replace(
                    tzinfo=dt_util.UTC
                )

                if not has_range(date_collected, price_interval):
                    continue

                if (
                    last_stats_time is not None
                    and date_collected <= last_stats_time + timedelta(days=1)
                ):
                    continue

                if ref_date is None:
                    value += value_collected
                    _LOGGER.debug("New loop :%s %s", date_collected, value_collected)
                    ref_date = date_collected
                elif date_collected.day == ref_date.day:
                    value += value_collected
                    _LOGGER.debug("Same days : %s %s", date_collected, value_collected)
                elif (
                    date_collected.time() == datetime.strptime("00:00", "%H:%M").time()
                ) and ref_date.time() != datetime.strptime("00:00", "%H:%M").time():
                    value += value_collected
                    _LOGGER.debug("Midnight : %s %s", date_collected, value_collected)
                elif ref_date:
                    date_ref = datetime.combine(ref_date, datetime.min.time()).replace(
                        tzinfo=dt_util.UTC
                    )

                    if get_sum := collects[name]["statistics"].get(date_ref):
                        value = get_sum[0] + value

                    summary += value
                    collects[name]["statistics"].update({date_ref: (value, summary)})
                    _LOGGER.debug("Collected : %s %s %s", date_ref, value, summary)
                    ref_date = date_collected
                    value = value_collected
                    _LOGGER.debug("%s %s", date_collected, value_collected)

            if value > 0:
                date_ref = datetime.combine(ref_date, datetime.min.time()).replace(
                    tzinfo=dt_util.UTC
                )
                if get_sum := collects[name]["statistics"].get(date_ref):
                    value = get_sum[0] + value
                summary += value
                collects[name]["statistics"].update({date_ref: (value, summary)})
                _LOGGER.debug("Collected : %s %s %s", date_ref, value, summary)

            name = name if name else statistic_id.split(":")[1]
            global_statistics.update({name: summary})
        if collects:
            for name, values in collects.items():
                statistics = []
                for date_ref, datas in collects[name]["statistics"].items():
                    statistics.append(
                        StatisticData(start=date_ref, state=datas[0], sum=datas[1])
                    )

                _LOGGER.debug("Add statistic %s to table", name)
                self.hass.async_add_executor_job(
                    async_add_external_statistics,
                    self.hass,
                    values["metadata"],
                    statistics,
                )

                _LOGGER.debug("Add %s cost", name)
                await self.async_insert_costs(
                    statistics, values["statistic_id"], values["price"]
                )
        return global_statistics

    async def async_load_datas_history(self, call):
        """Load datas in statics table."""
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get(call.data[CONF_DEVICE_ID])
        for entry_id in device.config_entries:
            if entry := self.hass.data[DOMAIN].get(entry_id):
                break

        query = call.data[CONF_POWER_MODE]
        if query in [CONSUMPTION_DAILY, CONSUMPTION_DETAIL]:
            power = CONSUMPTION
            cost = entry.options[CC]
        else:
            power = PRODUCTION
            cost = entry.options[PC]
        start = call.data[CONF_AFTER]
        statistic_id = f"{DOMAIN}:{entry.pdl}_{power}"

        rules = [
            {
                "name": power.lower(),
                "statistic_id": statistic_id.lower(),
                "price_interval": (None, "00H00", "00H00", cost),
            },
        ]

        stat = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            datetime.combine(start, datetime.min.time()).replace(tzinfo=dt_util.UTC),
            None,
            [statistic_id],
            "hour",
        )

        if stat.get(statistic_id):
            end = (
                dt_util.parse_datetime(stat[statistic_id][0]["start"])
                .replace(tzinfo=dt_util.UTC)
                .date()
            )
        else:
            end = call.data[CONF_BEFORE]

        await self._async_fetch_datas(query, rules, start, end)

    async def async_insert_costs(
        self, statistics: StatisticData, statistic_id: str, price: float
    ) -> None:
        """Insert costs."""
        if price <= 0:
            return
        last_stats = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics, self.hass, 1, statistic_id, True
        )
        cost_sum = 0 if not last_stats else last_stats[statistic_id][0]["sum"]

        costs = []
        for stat in statistics:
            cost = round(stat["state"] * price, 2)
            cost_sum += cost
            costs.append(StatisticData(start=stat["start"], state=cost, sum=cost_sum))

        if costs:
            name = statistic_id.split(":")[1]
            metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=f"{name}_cost",
                source=DOMAIN,
                statistic_id=f"{statistic_id}_cost",
                unit_of_measurement="EUR",
            )
            self.hass.async_add_executor_job(
                async_add_external_statistics, self.hass, metadata, costs
            )

    @classmethod
    def get_mode(self, entry: str) -> list(str, str):
        """Return mode."""
        collects = []
        pdl = entry.data.get(CONF_PDL)
        rules = entry.options.get(CONF_RULES, {})
        if entry.options[CONF_PRODUCTION] in [PRODUCTION_DAILY, PRODUCTION_DETAIL]:
            collects.append(
                {
                    "query": entry.options[CONF_PRODUCTION],
                    "start": self.minus_date(365)
                    if entry.options[CONF_PRODUCTION] in [PRODUCTION_DAILY]
                    else self.minus_date(6),
                    "end": datetime.now(),
                    "rules": [
                        {
                            "name": PRODUCTION.lower(),
                            "statistic_id": f"{DOMAIN}:{pdl}_{PRODUCTION}".lower(),
                            "price_interval": (
                                None,
                                "00H00",
                                "00H00",
                                entry.options[PC],
                            ),
                        },
                    ],
                }
            )
        if entry.options[CONF_CONSUMTPION] in [CONSUMPTION_DAILY] or (
            entry.options[CONF_CONSUMTPION] in [CONSUMPTION_DETAIL]
            and len(rules.keys()) == 0
        ):
            collects.append(
                {
                    "query": entry.options[CONF_CONSUMTPION],
                    "start": self.minus_date(365)
                    if entry.options[CONF_CONSUMTPION] in [CONSUMPTION_DAILY]
                    else self.minus_date(6),
                    "end": datetime.now(),
                    "rules": [
                        {
                            "name": CONSUMPTION.lower(),
                            "statistic_id": f"{DOMAIN}:{pdl}_{CONSUMPTION}".lower(),
                            "price_interval": (
                                None,
                                "00H00",
                                "00H00",
                                entry.options[CC],
                            ),
                        },
                    ],
                }
            )

        elif (
            entry.options[CONF_CONSUMTPION] in [CONSUMPTION_DETAIL]
            and len(rules.keys()) > 0
        ):
            datas_rules = []
            for rule in rules.values():
                datas_rules.append(
                    {
                        "name": f"{CONSUMPTION}_{rule[CONF_RULE_NAME]}".lower(),
                        "price_interval": (
                            rule[CONF_RULE_NAME],
                            rule[CONF_RULE_START_TIME],
                            rule[CONF_RULE_END_TIME],
                            rule[CONF_RULE_PRICE],
                        ),
                        "statistic_id": f"{DOMAIN}:{pdl}_{CONSUMPTION}_{rule[CONF_RULE_NAME]}".lower(),
                    }
                )

            collects.append(
                {
                    "query": entry.options[CONF_CONSUMTPION],
                    "start": self.minus_date(6),
                    "end": datetime.now(),
                    "rules": datas_rules,
                }
            )
        return collects

    @staticmethod
    def weighted_interval(interval: str) -> float | int:
        """Compute weighted."""
        if interval and len(rslt := re.findall("PT([0-9]{2})M", interval)) == 1:
            return int(rslt[0]) / 60
        return 1

    @staticmethod
    def minus_date(days: int) -> datetime:
        """Substract now."""
        return datetime.now() - timedelta(days=days)


def has_range(hour: datetime, price_interval: list) -> bool:
    """Check offpeak hour."""
    midnight = datetime.strptime("00H00", "%HH%M").time()
    start_time = hour.time()
    starting = datetime.strptime(price_interval[1], "%HH%M").time()
    ending = datetime.strptime(price_interval[2], "%HH%M").time()
    if start_time > starting and start_time <= ending:
        return True
    elif (ending == midnight) and (start_time > starting or start_time == midnight):
        return True
    return False
