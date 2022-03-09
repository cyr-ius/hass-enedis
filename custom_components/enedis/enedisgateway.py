"""Class for Enedis Gateway (http://enedisgateway.tech)."""
import logging
import re

import json
import requests
from requests.exceptions import RequestException
from sqlalchemy import create_engine


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

    def __init__(self, pdl, token, session=None, db=None):
        """Init."""
        self.pdl = str(pdl)
        self.token = token
        self.session = session if session else requests.Session()
        self.db = EnedisDatabase(self, db)

    async def _async_make_request(self, payload):
        """Request session."""
        headers = {"Authorization": self.token, "Content-Type": "application/json"}
        try:
            resp = await self.session.request(
                method="POST", url=API_URL, json=payload, headers=headers
            )
            response = await resp.json()
            if "error" in response:
                raise EnedisException(response.get("description"))
            if "tag" in response and response["tag"] in ["limit_reached", "enedis_return_ko"]:
                _LOGGER.warning(response.get("description"))
            return response
        except RequestException as error:
            raise EnedisException("Request failed") from error

    async def async_get_identity(self):
        """Get identity."""
        payload = {"type": "identity", "usage_point_id": str(self.pdl)}
        return await self._async_make_request(payload)

    async def async_get_addresses(self):
        """Get addresses."""
        addresses = await self.db.async_get_addresses(self.pdl)
        if addresses is None or len(addresses) == 0:
            payload = {"type": "addresses", "usage_point_id": str(self.pdl)}
            addresses = await self._async_make_request(payload)
            await self.db.async_update_addresses(self.pdl, addresses)
        return addresses

    async def async_get_contracts(self):
        """Get contracts."""
        contracts = await self.db.async_get_contracts(self.pdl)
        if contracts is None or len(contracts) == 0:
            payload = {"type": "contracts", "usage_point_id": str(self.pdl)}
            contracts = await self._async_make_request(payload)
            await self.db.async_update_contracts(self.pdl, contracts)
        return contracts

    async def async_get_max_power(self, start, end):
        """Get consumption max power."""
        payload = {
            "type": "daily_consumption_max_power",
            "usage_point_id": self.pdl,
            "start": f"{start}",
            "end": f"{end}",
        }
        return await self._async_make_request(payload)

    async def async_get_sum(self, service, start, end):
        """Get power."""
        payload = {
            "type": f"daily_{service}",
            "usage_point_id": f"{self.pdl}",
            "start": f"{start}",
            "end": f"{end}",
        }
        measurements = await self._async_make_request(payload)
        await self.db.async_update(self.pdl, measurements)
        measurements = await self.db.async_get_sum(self.pdl, service, start, end)
        return measurements

    async def async_get_detail(self, service, start, end):
        """Fetch datas."""
        payload = {
            "type": f"{service}_load_curve",
            "usage_point_id": f"{self.pdl}",
            "start": f"{start}",
            "end": f"{end}",
        }
        measurements = await self._async_make_request(payload)
        await self.db.async_update(self.pdl, measurements, True)
        measurements = await self.db.async_get(self.pdl, service, start, end)
        return measurements

    async def async_get_contract_by_pdl(self):
        """Return all."""
        datas = {}
        contracts = await self.async_get_contracts()
        for contract in contracts.get("customer", {}).get("usage_points"):
            if contract.get("usage_point", {}).get("usage_point_id") == self.pdl:
                datas.update(contract.get("contracts"))

        return datas


class EnedisException(Exception):
    """Enedis exception."""


class EnedisDatabase:
    """Enedis Gateway Database."""

    def __init__(self, api, db):
        """Init db."""
        self.api = api
        self.db = db
        self.con = create_engine(f"sqlite:///{self.db}")
        self.init_database()

    def init_database(self):
        """Initialize database."""
        result = self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        records = result.fetchall()
        if len(records) > 0:
            return

        """ADDRESSES"""
        self.con.execute(
            """CREATE TABLE addresses (pdl TEXT PRIMARY KEY,json json NOT NULL)"""
        )
        self.con.execute("""CREATE UNIQUE INDEX idx_pdl_addresses ON addresses (pdl)""")

        """CONTRACT"""
        self.con.execute(
            """CREATE TABLE contracts (pdl TEXT PRIMARY KEY, json json NOT NULL)"""
        )
        self.con.execute("""CREATE UNIQUE INDEX idx_pdl_contracts ON contracts (pdl)""")

        """CONSUMPTION DAILY."""
        self.con.execute(
            """CREATE TABLE consumption_daily (pdl TEXT NOT NULL,date DATE NOT NULL,value INTEGER NOT NULL)"""
        )
        self.con.execute(
            """CREATE UNIQUE INDEX idx_date_consumption ON consumption_daily (date)"""
        )

        """CONSUMPTION DAILY DETAIL."""
        self.con.execute(
            """CREATE TABLE consumption_detail (
                            pdl TEXT NOT NULL,
                            date DATETIME NOT NULL,
                            value INTEGER NOT NULL,
                            interval INTEGER NOT NULL,
                            measure_type TEXT NOT NULL)"""
        )
        self.con.execute(
            """CREATE UNIQUE INDEX idx_date_consumption_detail ON consumption_detail (date)"""
        )

        """PRODUCTION DAILY."""
        self.con.execute(
            """CREATE TABLE production_daily (pdl TEXT NOT NULL,date DATE NOT NULL,value INTEGER NOT NULL)"""
        )
        self.con.execute(
            """CREATE UNIQUE INDEX idx_date_production ON production_daily (date)"""
        )

        """PRODUCTION DAILY DETAIL."""
        self.con.execute(
            """CREATE TABLE production_detail (
                            pdl TEXT NOT NULL,
                            date DATETIME NOT NULL,
                            value INTEGER NOT NULL,
                            interval INTEGER NOT NULL,
                            measure_type TEXT NOT NULL)"""
        )
        self.con.execute(
            """CREATE UNIQUE INDEX idx_date_production_detail ON production_detail (date)"""
        )

    async def async_get_contracts(self, pdl):
        """Get contracts."""
        query = f"SELECT json FROM contracts WHERE pdl = '{pdl}'"
        result = self.con.execute(query)
        rows = result.fetchone()
        if rows is None:
            return {}
        return json.loads(rows[0])

    async def async_get_addresses(self, pdl):
        """Get addresses."""
        query = f"SELECT json FROM addresses WHERE pdl = '{pdl}'"
        result = self.con.execute(query)
        rows = result.fetchone()
        if rows is None:
            return {}
        return json.loads(rows[0])

    async def async_get_sum(self, pdl, service, start=None, end=None):
        """Get summary power."""
        table = f"{service}_daily"
        query = f"SELECT sum(value) as summary FROM {table} WHERE pdl == '{pdl}' ORDER BY date;"
        if start:
            query = f"SELECT sum(value) as {service}_summary FROM {table} WHERE pdl == '{pdl}' AND date BETWEEN '{start}' AND '{end}' ORDER BY DATE DESC;"
        cur = self.con.execute(query)
        rows = cur.fetchone()
        if rows is None or len(rows) == 0:
            return 0
        return dict(zip(rows.keys(), rows))

    async def async_get(self, pdl, service, start=None, end=None):
        """Get power detailed."""
        table = f"{service}_detail"
        query = f"SELECT value FROM {table} WHERE pdl == '{pdl}' ORDER BY DATE DESC;"
        if start:
            query = f"SELECT value FROM {table} WHERE pdl == '{pdl}' AND date BETWEEN '{start}' AND '{end}' ORDER BY DATE DESC;"
        cur = self.con.execute(query)
        rows = cur.fetchall()
        if len(rows) == 0:
            return {}
        return dict(zip(rows.keys(), rows))

    async def async_update_contracts(self, pdl, contracts):
        """Update contracts."""
        query = "INSERT OR REPLACE INTO contracts VALUES (?,?)"
        self.con.execute(query, [pdl, json.dumps(contracts)])

    async def async_update_addresses(self, pdl, addresses):
        """Update addresses."""
        query = "INSERT OR REPLACE INTO addresses VALUES (?,?)"
        self.con.execute(query, [pdl, json.dumps(addresses)])

    async def async_update(self, service, measurements, detail=False):
        """Update power."""
        if (meter_reading := measurements.get("meter_reading")) and (
            interval_reading := measurements.get("meter_reading").get(
                "interval_reading"
            )
        ):
            pdl = meter_reading.get("usage_point_id")
            if detail:
                table = (
                    PRODUCTION_DETAIL if service == "production" else CONSUMPTION_DETAIL
                )
                config_query = f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?, ?, ?)"
                for interval in interval_reading:
                    interval_length = re.findall(
                        r"PT([0-9]+)M", interval.get("interval_length")
                    )[0]
                    self.con.execute(
                        config_query,
                        [
                            pdl,
                            interval.get("date"),
                            interval.get("value"),
                            interval_length,
                            interval.get("measure_type"),
                        ],
                    )
            else:
                table = PRODUCTION if service == "production" else CONSUMPTION
                config_query = f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?)"
                for interval in interval_reading:
                    self.con.execute(
                        config_query, [pdl, interval.get("date"), interval.get("value")]
                    )
