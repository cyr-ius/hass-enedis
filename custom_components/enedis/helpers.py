"""Helper module."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging

from myelectricaldatapy import EnedisAnalytics, EnedisByPDL, EnedisException

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    clear_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.const import ENERGY_KILO_WATT_HOUR
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util

from .const import (
    CONF_END_DATE,
    CONF_ENTRY,
    CONF_POWER_MODE,
    CONF_RULE_END_TIME,
    CONF_RULE_NAME,
    CONF_RULE_PERIOD,
    CONF_RULE_PRICE,
    CONF_RULE_START_TIME,
    CONF_START_DATE,
    CONF_STATISTIC_ID,
    CONSUMPTION,
    CONSUMPTION_DAILY,
    CONSUMPTION_DETAIL,
    COST_CONSUMPTION,
    COST_PRODUCTION,
    DOMAIN,
    PRODUCTION,
)

_LOGGER = logging.getLogger(__name__)


async def async_fetch_datas(
    api: EnedisByPDL, pdl: str, service: str, start_date: datetime, end_date: datetime
) -> dict:
    """Fetch datas."""
    rslt = {}
    try:
        rslt = await api.async_fetch_datas(service, pdl, start_date, end_date)
    except EnedisException as error:
        _LOGGER.error(error)
    return rslt.get("meter_reading", {}).get("interval_reading", [])


async def async_statistics(hass: HomeAssistant, dataset: dict, rules: list = None):
    """Compute statistics."""
    global_statistics = {}
    for statistic_id, rule in rules.items():
        _LOGGER.debug("%s stat", statistic_id)
        name = rule[CONF_RULE_NAME]

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
            else last_stats[statistic_id][0]["start"].strftime("%Y-%m-%d")
        )
        _LOGGER.debug("Start date : %s", last_stats_time)

        analytics = EnedisAnalytics(dataset)
        datas_collected = analytics.get_data_analytcis(
            convertKwh=True,
            convertUTC=True,
            start_date=last_stats_time,
            intervals=rule[CONF_RULE_PERIOD],
            groupby="date",
            freq="D",
            summary=True,
            cumsum=summary,
        )

        datas_collected = analytics.set_price(
            datas_collected, rule[CONF_RULE_PRICE], True
        )
        _LOGGER.debug(datas_collected)

        if sum_value := analytics.get_last_value(datas_collected, "date", "sum_value"):
            summary = sum_value

        if rule.get("disabled") is None:
            global_statistics.update({name: summary})

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


def dateatmidnight(date: datetime):
    """Return date at midnight , ex 01/01/2000 00h00."""
    return datetime.combine(date, datetime.min.time()).replace(tzinfo=dt_util.UTC)


def minus_date(days: int) -> datetime:
    """Substract now."""
    return datetime.now() - timedelta(days=days)


def rules_format(pdl: str, power: str, rules: dict[str, str]) -> dict[str, str]:
    """Construct rules."""
    datas_rules = {}
    for rule in rules.values():
        id = f"{DOMAIN}:{pdl}_{power}_{rule[CONF_RULE_NAME]}".lower()
        # Create empty dict
        if not datas_rules.get(id):
            datas_rules.update({id: {CONF_RULE_PERIOD: []}})

        # Add attributs
        datas_rules[id][CONF_RULE_PERIOD].append(
            (rule[CONF_RULE_START_TIME], rule[CONF_RULE_END_TIME])
        )
        datas_rules[id][CONF_RULE_PRICE] = rule[CONF_RULE_PRICE]
        datas_rules[id][CONF_RULE_NAME] = f"{power}_{rule[CONF_RULE_NAME]}".lower()

    return datas_rules


async def async_service_load_datas_history(
    hass: HomeAssistant, api: EnedisByPDL, call: ServiceCall
):
    """Load datas in statics table."""
    entry_id = call.data[CONF_ENTRY]
    entry = hass.data[DOMAIN].get(entry_id)
    query = call.data[CONF_POWER_MODE]
    if query in [CONSUMPTION_DAILY, CONSUMPTION_DETAIL]:
        power = CONSUMPTION
        cost = entry.config_entry.options[COST_CONSUMPTION]
    else:
        power = PRODUCTION
        cost = entry.config_entry.options[COST_PRODUCTION]

    start = call.data[CONF_START_DATE]
    statistic_id = f"{DOMAIN}:{entry.pdl}_{power}"
    stat = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        dateatmidnight(start),
        None,
        [statistic_id],
        "day",
        None,
        "sum",
    )
    end = (
        dt_util.parse_datetime(stat[statistic_id][0]["start"])
        .replace(tzinfo=dt_util.UTC)
        .date()
        if stat.get(statistic_id)
        else call.data[CONF_END_DATE]
    )

    rules = {
        f"{DOMAIN}:{entry.pdl}_{power}": {
            CONF_RULE_NAME: power,
            CONF_RULE_PRICE: cost,
            CONF_RULE_PERIOD: [("00:00:00", "00:00:00")],
        }
    }

    # Fetch datas
    dataset = await async_fetch_datas(api, entry.pdl, query, start, end)
    # Add statistics in HA Database
    await async_statistics(hass, dataset, rules)


async def async_service_datas_clear(hass: HomeAssistant, call: ServiceCall):
    """Clear data in database."""
    statistic_id = call.data[CONF_STATISTIC_ID]
    if not statistic_id.startswith("enedis:"):
        _LOGGER.error("statistic_id is incorrect %s", statistic_id)
        return
    hass.async_add_executor_job(clear_statistics, get_instance(hass), [statistic_id])
