"""Class for Enedis Gateway (http://enedisgateway.tech)."""
import logging
import re
import sqlite3
from datetime import datetime, timedelta

import requests
from requests.exceptions import RequestException

URL = "https://enedisgateway.tech"
API_URL = f"{URL}/api"
MANUFACTURER = "Enedis"
PRODUCTION = "production_daily"
PRODUCTION_DETAIL = "production_detail"
CONSUMPTION = "consumption_daily"
CONSUMPTION_DETAIL = "consumption_detail"

_LOGGER = logging.getLogger(__name__)


class EnedisGateway:
    """Class for Enedis Gateway API."""

    def __init__(self, pdl, token, session=None):
        """Init."""
        self.pdl = pdl
        self.token = token
        self.session = session if session else requests.Session()
        self.db = EnedisDatabase(self)

    async def _async_make_request(self, service, start=None, end=None):
        """Request session."""
        headers = {"Authorization": self.token, "Content-Type": "application/json"}

        try:
            payload = {
                "type": f"{service}",
                "usage_point_id": f"{self.pdl}",
                "start": f"{start}",
                "end": f"{end}",
            }
            response = await self.session.request(
                method="POST", url=API_URL, json=payload, headers=headers
            )
            json = await response.json()
            if "error" in json:
                raise EnedisException(json.get("description"))
            if "tag" in json and json["tag"] == "limit_reached":
                raise LimitException(json.get("description"))
            return json
        except RequestException as error:
            raise EnedisException("Request failed") from error

    async def async_get_identity(self):
        """Get identity."""
        return await self._async_make_request("identity")

    async def async_get_addresses(self):
        """Get addresses."""
        return await self._async_make_request("addresses")

    async def async_get_contracts(self):
        """Get contracts."""
        return await self._async_make_request("contracts")

    async def async_get_max_power(self, start_date, end_date):
        """Get consumption max power."""
        return await self._async_make_request(
            "daily_consumption_max_power", start_date, end_date
        )

    async def async_fetch_datas(
        self, start_date, end_date, data_type="consumption", curve=False
    ):
        """Fetch datas."""
        if curve:
            return await self._async_make_request(
                f"{data_type}_load_curve", start_date, end_date
            )
        return await self._async_make_request(
            f"daily_{data_type}", start_date, end_date
        )


class EnedisException(Exception):
    """Enedis exception."""


class LimitException(EnedisException):
    """Limit reached exception."""


class EnedisDatabase:
    """Enedis Gateway Database."""

    def __init__(self, api):
        """Init db."""
        self.api = api
        self.con = sqlite3.connect("config/enedis-gateway.db", timeout=10)
        self.cur = self.con.cursor()
        self.init_database()

    def init_database(self):
        """Initialize database."""
        self.cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        query_result = self.cur.fetchall()
        if len(query_result) > 0:
            return

        """CONSUMPTION DAILY."""
        self.cur.execute(
            """CREATE TABLE consumption_daily (pdl TEXT NOT NULL,date DATE NOT NULL,value INTEGER NOT NULL)"""
        )
        self.cur.execute(
            """CREATE UNIQUE INDEX idx_date_consumption ON consumption_daily (date)"""
        )

        """CONSUMPTION DAILY DETAIL."""
        self.cur.execute(
            """CREATE TABLE consumption_detail (
                            pdl TEXT NOT NULL,
                            date DATETIME NOT NULL,
                            value INTEGER NOT NULL,
                            interval INTEGER NOT NULL,
                            measure_type TEXT NOT NULL)"""
        )
        self.cur.execute(
            """CREATE UNIQUE INDEX idx_date_consumption_detail ON consumption_detail (date)"""
        )

        """PRODUCTION DAILY."""
        self.cur.execute(
            """CREATE TABLE production_daily (pdl TEXT NOT NULL,date DATE NOT NULL,value INTEGER NOT NULL)"""
        )
        self.cur.execute(
            """CREATE UNIQUE INDEX idx_date_production ON production_daily (date)"""
        )

        """PRODUCTION DAILY DETAIL."""
        self.cur.execute(
            """CREATE TABLE production_detail (
                            pdl TEXT NOT NULL,
                            date DATETIME NOT NULL,
                            value INTEGER NOT NULL,
                            interval INTEGER NOT NULL,
                            measure_type TEXT NOT NULL)"""
        )
        self.cur.execute(
            """CREATE UNIQUE INDEX idx_date_production_detail ON production_detail (date)"""
        )

    async def async_update(self, data_type="consumption"):
        """Update power."""
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() + timedelta(days=-6)).strftime("%Y-%m-%d")
        table = PRODUCTION if data_type == "production" else CONSUMPTION

        rslts = await self.api.async_fetch_datas(start_date, end_date, data_type)

        if (meter_reading := rslts.get("meter_reading")) and (
            interval_reading := rslts.get("meter_reading").get("interval_reading")
        ):
            pdl = meter_reading.get("usage_point_id")
            config_query = f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?)"
            for interval in interval_reading:
                self.cur.execute(
                    config_query, [pdl, interval.get("date"), interval.get("value")]
                )
                self.con.commit()
        _LOGGER.warning(rslts.get("description"))

    async def async_update_detail(self, data_type="consumption"):
        """Update power detail."""
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() + timedelta(days=-6)).strftime("%Y-%m-%d")
        table = PRODUCTION_DETAIL if data_type == "production" else CONSUMPTION_DETAIL

        rslts = await self.api.async_fetch_datas(start_date, end_date, data_type, True)

        if (meter_reading := rslts.get("meter_reading")) and (
            interval_reading := rslts.get("meter_reading").get("interval_reading")
        ):
            pdl = meter_reading.get("usage_point_id")
            config_query = f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?, ?, ?)"
            for interval in interval_reading:
                interval_length = re.findall(
                    r"PT([0-9]+)M", interval.get("interval_length")
                )[0]
                self.cur.execute(
                    config_query,
                    [
                        pdl,
                        interval.get("date"),
                        interval.get("value"),
                        interval_length,
                        interval.get("measure_type"),
                    ],
                )
                self.con.commit()
        _LOGGER.warning(rslts.get("description"))

    async def async_get_sum(self, pdl, start=None, end=None, table=CONSUMPTION):
        """Get summary power."""
        query = (
            f"SELECT pdl, sum(value) FROM {table} WHERE pdl == '{pdl}' ORDER BY date;"
        )
        if start:
            query = f"SELECT pdl, sum(value) FROM {table} WHERE pdl == '{pdl}' AND date BETWEEN '{start}' AND '{end}' ORDER BY DATE DESC;"
        self.cur.execute(query)
        pdl, power = self.cur.fetchone()
        power = power if power else 0
        return {"pdl": pdl, "total_power": int(power) / 1000}

    async def async_get(self, pdl, start=None, end=None, table=CONSUMPTION):
        """Get power detailed."""
        query = f"SELECT * FROM {table} WHERE pdl == '{pdl}' ORDER BY DATE DESC;"
        if start:
            query = f"SELECT * FROM {table} WHERE pdl == '{pdl}' AND date BETWEEN '{start}' AND '{end}' ORDER BY DATE DESC;"
        self.cur.execute(query)
        query_result = self.cur.fetall()
        return query_result
