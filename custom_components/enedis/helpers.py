"""Helper module."""

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
from homeassistant.const import (
    CONF_AFTER,
    CONF_BEFORE,
    CONF_DEVICE_ID,
    CONF_NAME,
    ENERGY_KILO_WATT_HOUR,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .const import (
    CONF_POWER_MODE,
    CONF_RULE_END_TIME,
    CONF_RULE_NAME,
    CONF_RULE_PRICE,
    CONF_RULE_START_TIME,
    CONF_STATISTIC_ID,
    CONSUMPTION,
    CONSUMPTION_DAILY,
    CONSUMPTION_DETAIL,
    COST_CONSUMTPION,
    COST_PRODUCTION,
    DOMAIN,
    PRODUCTION,
)

_LOGGER = logging.getLogger(__name__)


async def async_fetch_datas(
    hass: HomeAssistant,
    api: EnedisByPDL,
    query: str,
    rules: list,
    after: datetime,
    before: datetime,
) -> dict:
    """Fetch datas."""
    datas_collected = []
    try:
        # Collect interval
        datas = await api.async_fetch_datas(query, after, before)
        datas_collected = datas.get("meter_reading", {}).get("interval_reading", [])
    except EnedisException as error:
        _LOGGER.error(error)
    return await async_statistics(hass, datas_collected, rules)


async def async_statistics(hass: HomeAssistant, datas_collected, rules: list = None):
    """Compute statistics."""
    global_statistics = {}
    collects = {}
    for rule in rules:
        statistic_id = rule[CONF_STATISTIC_ID]
        name = rule[CONF_NAME]

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
                        "price": rule[CONF_RULE_PRICE],
                        CONF_STATISTIC_ID: statistic_id,
                    }
                }
            )

        # Fetch last information in database
        last_stats = await get_instance(hass).async_add_executor_job(
            get_last_statistics, hass, 1, statistic_id, True
        )

        # Fetch last sum in database
        summary = 0 if not last_stats else last_stats[statistic_id][0]["sum"]

        # Fetch last time in database
        last_stats_time = (
            None
            if not last_stats
            else dt_util.parse_datetime(last_stats[statistic_id][0]["start"])
        )

        ref_date = None
        value = 0
        for data in datas_collected:
            if (value_collected := int(data.get("value"))) is None:
                continue

            interval = float(weighted_interval(data.get("interval_length")))
            value_collected = value_collected / 1000 * interval  # Convert Wh to Kwh

            date_collected = dt_util.parse_datetime(data["date"]).replace(
                tzinfo=dt_util.UTC
            )

            if not has_range(
                date_collected, rule[CONF_RULE_START_TIME], rule[CONF_RULE_END_TIME]
            ):
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

        if rule.get("disabled") is None:
            global_statistics.update({name: summary})

    for name, values in collects.items():
        statistics = []
        for date_ref, datas in collects[name]["statistics"].items():
            statistics.append(
                StatisticData(start=date_ref, state=datas[0], sum=datas[1])
            )
            if statistics:
                _LOGGER.debug("Add statistic %s to table", name)
                hass.async_add_executor_job(
                    async_add_external_statistics,
                    hass,
                    values["metadata"],
                    statistics,
                )

                _LOGGER.debug("Add %s cost", name)
                await async_insert_costs(
                    statistics, values[CONF_STATISTIC_ID], values["price"]
                )
    return global_statistics


async def async_insert_costs(
    hass: HomeAssistant, statistics: StatisticData, statistic_id: str, price: float
) -> None:
    """Insert costs."""
    if price <= 0:
        return
    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True
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
        hass.async_add_executor_job(
            async_add_external_statistics, hass, metadata, costs
        )


def weighted_interval(interval: str) -> float | int:
    """Compute weighted."""
    if interval and len(rslt := re.findall("PT([0-9]{2})M", interval)) == 1:
        return int(rslt[0]) / 60
    return 1


def has_range(hour: datetime, start: str, end: str) -> bool:
    """Check offpeak hour."""
    midnight = datetime.strptime("00H00", "%HH%M").time()
    start_time = hour.time()
    starting = datetime.strptime(start, "%HH%M").time()
    ending = datetime.strptime(end, "%HH%M").time()
    if start_time > starting and start_time <= ending:
        return True
    elif (ending == midnight) and (start_time > starting or start_time == midnight):
        return True
    return False


async def async_service_load_datas_history(hass: HomeAssistant, api: EnedisByPDL, call: ServiceCall):
    """Load datas in statics table."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(call.data[CONF_DEVICE_ID])
    for entry_id in device.config_entries:
        if entry := hass.data[DOMAIN].get(entry_id):
            break

    query = call.data[CONF_POWER_MODE]
    if query in [CONSUMPTION_DAILY, CONSUMPTION_DETAIL]:
        power = CONSUMPTION
        cost = entry.config_entry.options[COST_CONSUMTPION]
    else:
        power = PRODUCTION
        cost = entry.config_entry.options[COST_PRODUCTION]
    start = call.data[CONF_AFTER]
    statistic_id = f"{DOMAIN}:{entry.pdl}_{power}"

    rules = [
        {
            CONF_NAME: power.lower(),
            CONF_STATISTIC_ID: statistic_id.lower(),
            CONF_RULE_NAME: None,
            CONF_RULE_START_TIME: "00H00",
            CONF_RULE_END_TIME: "00H00",
            CONF_RULE_PRICE: cost,
            "disabled": True,
        },
    ]

    stat = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
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

    await async_fetch_datas(hass, api, query, rules, start, end)
