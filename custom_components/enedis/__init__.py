"""The Enedis integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import voluptuous as vol
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN, ENERGY_KILO_WATT_HOUR
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CONSUMPTION,
    CONF_CONSUMPTION_DETAIL,
    CONF_PDL,
    CONF_PRODUCTION,
    CONF_PRODUCTION_DETAIL,
    COORDINATOR,
    DOMAIN,
    JSON,
    PLATFORMS,
    UNDO_LISTENER,
)
from .enedisgateway import MANUFACTURER, URL, EnedisException, EnedisGateway

CONFIG_SCHEMA = vol.Schema({vol.Optional(DOMAIN): {}}, extra=vol.ALLOW_EXTRA)
SCAN_INTERVAL = timedelta(hours=1)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Enedis integration."""
    return True


async def async_setup_entry(hass, config_entry):
    """Set up Enedis as config entry."""
    hass.data.setdefault(DOMAIN, {})
    pdl = config_entry.data.get(CONF_PDL)

    coordinator = EnedisDataUpdateCoordinator(hass, config_entry)
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

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Class to manage fetching data API."""
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.session = async_create_clientsession(hass)
        self.config = config_entry.data
        self.options = config_entry.options
        self.pdl = self.config[CONF_PDL]
        self.enedis = EnedisGateway(
            pdl=self.config[CONF_PDL],
            token=self.config[CONF_TOKEN],
            session=self.session,
        )
        self.statistics = {}

    async def _async_update_data(self):
        """Update data via API."""
        contracts = await self.enedis.async_get_contract_by_pdl()
        consumption = await self._insert_statistics("consumption")
        return {"contracts": contracts, "consumption": consumption}

    async def _insert_statistics(self, service) -> dict:
        """Update and fetch datas."""
        start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
        datas  = await self.enedis.async_get_datas("consumption", start, end)
        hourly_consumption_data = datas.get("meter_reading", {}).get("interval_reading")

        unit = ENERGY_KILO_WATT_HOUR

        statistic_id = f"{DOMAIN}:{service}_summary_{self.pdl}"
        last_stats = await self.hass.async_add_executor_job(
            get_last_statistics, self.hass, 1, statistic_id, True
        )
        if not last_stats:
            _sum = 0
            last_stats_time = None
        else:
            start = dt_util.parse_datetime(
                hourly_consumption_data[0]["date"]
            ) - timedelta(hours=1)
            start = dt_util.parse_datetime(
                hourly_consumption_data[len(hourly_consumption_data) - 1]["date"]
            ).astimezone() - timedelta(hours=1)
            stat = await self.hass.async_add_executor_job(
                statistics_during_period,
                self.hass,
                start,
                None,
                [statistic_id],
                "hour",
                True,
            )
            _sum = stat[statistic_id][1]["sum"]
            last_stats_time = stat[statistic_id][1]["start"]

        statistics = []
        for data in hourly_consumption_data:
            if (value := data.get("value")) is None:
                continue

            start = dt_util.parse_datetime(data["date"]).astimezone()
            if last_stats_time is not None and start <= last_stats_time:
                continue

            _sum += int(value) /1000
            statistics.append(
                StatisticData(
                    start=start,
                    state=int(value) /1000 ,
                    sum=_sum,
                )
            )

        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=f"Total {service} ({self.pdl})",
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_of_measurement=unit,
        )

        async_add_external_statistics(self.hass, metadata, statistics)

        return _sum
