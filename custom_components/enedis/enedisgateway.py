"""Class for Enedis Gateway (http://enedisgateway.tech)."""

import json
import logging
import re
from datetime import timedelta, date, datetime

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

    def __init__(self, pdl, token, session=None):
        """Init."""
        self.pdl = str(pdl)
        self.token = token
        self.session = session if session else requests.Session()

    async def _async_make_request(self, payload):
        """Request session."""
        headers = {"Authorization": self.token, "Content-Type": "application/json"}
        try:
            _LOGGER.debug(f"Make request {payload}")
            resp = await self.session.request(
                method="POST", url=API_URL, json=payload, headers=headers
            )
            response = await resp.json()
            if "error" in response:
                raise EnedisGatewayException(response.get("description"))
            if "tag" in response and response["tag"] in [
                "limit_reached",
                "enedis_return_ko",
            ]:
                raise EnedisGatewayException(response.get("description"))
            return response
        except RequestException as error:
            raise EnedisGatewayException("Request failed") from error

    async def async_get_identity(self):
        """Get identity."""
        payload = {"type": "identity", "usage_point_id": str(self.pdl)}
        return await self._async_make_request(payload)

    async def async_get_addresses(self):
        """Get addresses."""
        payload = {"type": "addresses", "usage_point_id": str(self.pdl)}
        return await self._async_make_request(payload)

    async def async_get_contracts(self):
        """Get contracts."""
        payload = {"type": "contracts", "usage_point_id": str(self.pdl)}
        return await self._async_make_request(payload)

    async def async_get_max_power(self, start, end):
        """Get consumption max power."""
        payload = {
            "type": "daily_consumption_max_power",
            "usage_point_id": self.pdl,
            "start": f"{start}",
            "end": f"{end}",
        }
        return await self._async_make_request(payload)

    async def async_get_datas(self, service, start, end, detail=False):
        """Get datas."""
        payload = {
            "type": f"daily_{service}",
            "usage_point_id": f"{self.pdl}",
            "start": f"{start}",
            "end": f"{end}",
        }
        if detail:
            payload = {
                "type": f"{service}_load_curve",
                "usage_point_id": f"{self.pdl}",
                "start": f"{start}",
                "end": f"{end}",
            }

        return await self._async_make_request(payload)


class Enedis:
    """Enedis Gateway Database."""

    def __init__(self, pdl, token, db, session=None):
        """Init db."""
        self.db = db
        self.con = create_engine(f"sqlite:///{self.db}")
        self.init_database()
        self.api = EnedisGateway(pdl, token, session)
        self.pdl = pdl

    def init_database(self):
        """Initialize database."""
        tables = []
        result = self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        records = result.fetchall()
        if len(records) > 0:
            tables = [row[0] for row in records]

        if "addresses" not in tables:
            _LOGGER.debug("Create addresses table")
            self.con.execute(
                """CREATE TABLE addresses (pdl TEXT PRIMARY KEY,json json NOT NULL)"""
            )
            self.con.execute(
                """CREATE UNIQUE INDEX idx_pdl_addresses ON addresses (pdl)"""
            )

        if "contracts" not in tables:
            _LOGGER.debug("Create contracts table")
            self.con.execute(
                """CREATE TABLE contracts (pdl TEXT PRIMARY KEY, json json NOT NULL)"""
            )
            self.con.execute(
                """CREATE UNIQUE INDEX idx_pdl_contracts ON contracts (pdl)"""
            )

        if "consumption_daily" not in tables:
            _LOGGER.debug("Create consumption_daily table")
            self.con.execute(
                """CREATE TABLE consumption_daily (pdl TEXT NOT NULL,date DATE NOT NULL,value INTEGER NOT NULL)"""
            )
            self.con.execute(
                """CREATE UNIQUE INDEX idx_date_consumption ON consumption_daily (date)"""
            )

        if "consumption_detail" not in tables:
            _LOGGER.debug("Create consumption_detail table")
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

        if "production_daily" not in tables:
            _LOGGER.debug("Create production_daily table")
            self.con.execute(
                """CREATE TABLE production_daily (pdl TEXT NOT NULL,date DATE NOT NULL,value INTEGER NOT NULL)"""
            )
            self.con.execute(
                """CREATE UNIQUE INDEX idx_date_production ON production_daily (date)"""
            )

        if "production_detail" not in tables:
            _LOGGER.debug("Create production_detail table")
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

        if "service_summary" not in tables:
            _LOGGER.debug("Create service_summary table")
            self.con.execute(
                """CREATE TABLE service_summary (pdl TEXT NOT NULL,service TEXT NOT NULL,value INTEGER NOT NULL,last_date DATE NOT NULL, PRIMARY KEY (pdl, service))"""
            )
            self.con.execute(
                """CREATE UNIQUE INDEX idx_pdl_service__service_summary ON service_summary (pdl,service)"""
            )

    async def async_get_identity(self):
        """Get identity."""
        return await self.api.async_get_identity()

    async def async_get_information_by_pdl(
        self,
        pdl,
        consumption=(False, False),
        production=(False, False),
    ):
        """Get all informations by pdl."""
        start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
        informations = {
            "contracts": await self.async_get_contract_by_pdl(pdl),
            "addresses": await self.async_get_addresses_by_pdl(pdl),
            "consumption": {},
            "production": {},
        }
        if consumption[0]:
            informations["consumption"].update(
                {
                    "weekly": await self.async_get_weekly(pdl, "consumption"),
                    "summary": await self.async_get_summary(pdl, "consumption"),
                }
            )

        if consumption[1]:
            informations["consumption"].update(
                {"detail": await self.async_get(pdl, "consumption", start, end)}
            )

        if production[0]:
            informations["production"].update(
                {
                    "weekly": await self.async_get_weekly(pdl, "production"),
                    "summary": await self.async_get_summary(pdl, "production"),
                }
            )
        if production[1]:
            informations["production"].update(
                {"detail": await self.async_get(pdl, "production", start, end)}
            )

        return informations

    async def async_get_contracts(self, pdl):
        """Get contracts."""
        query = f"SELECT json FROM contracts WHERE pdl = '{pdl}'"
        result = self.con.execute(query)
        rows = result.fetchone()
        if rows is None:
            contracts = await self.api.async_get_contracts()
            await self._async_update_contracts(contracts)
            return json.dumps(contracts)
        return json.loads(rows[0])

    async def async_get_contract_by_pdl(self, pdl):
        """Return all."""
        datas = {}
        contracts = await self.async_get_contracts(pdl)
        for contract in contracts.get("customer", {}).get("usage_points"):
            if contract.get("usage_point", {}).get("usage_point_id") == pdl:
                datas.update(contract.get("contracts"))
        return datas

    async def async_get_addresses(self, pdl):
        """Get addresses."""
        query = f"SELECT json FROM addresses WHERE pdl = '{pdl}'"
        result = self.con.execute(query)
        rows = result.fetchone()
        if rows is None:
            addresses = await self.api.async_get_addresses()
            await self._async_update_addresses(pdl, addresses)(addresses)
            return json.dumps(addresses)
        return json.loads(rows[0])

    async def async_get_addresses_by_pdl(self, pdl):
        """Return all."""
        datas = {}
        addresses = await self.async_get_addresses(pdl)
        for addresses in addresses.get("customer", {}).get("usage_points"):
            if addresses.get("usage_point", {}).get("usage_point_id") == pdl:
                datas.update(addresses.get("usage_point"))
        return datas

    async def async_get(self, pdl, service, start=None, end=None):
        """Get power detailed."""
        table = f"{service}_detail"
        query = f"SELECT value FROM {table} WHERE pdl == '{pdl}' ORDER BY DATE DESC;"
        if start:
            query = f"SELECT date, value FROM {table} WHERE pdl == '{pdl}' AND date BETWEEN '{start}' AND '{end}' ORDER BY DATE DESC;"
        rows = self.con.execute(query).fetchall()
        if rows is None or len(rows) == 0:
            return []
        return [dict(zip(row.keys(), row)) for row in rows]

    async def async_get_weekly(self, pdl, service):
        """Get weekly power."""
        table = f"{service}_daily"
        today = date.today()
        lastweek = today - timedelta(days=7)
        query = f"SELECT date, value FROM {table} WHERE pdl == '{pdl}' AND date BETWEEN '{lastweek}' AND '{today}' ORDER BY DATE DESC;"
        rows = self.con.execute(query).fetchall()
        if rows is None or len(rows) == 0:
            return []
        return [dict(zip(row.keys(), row)) for row in rows]

    async def async_get_summary(self, pdl, service):
        """Fetch data summary."""
        summary = 0
        query = f"SELECT value  FROM service_summary WHERE pdl == '{pdl}' AND service == '{service}';"
        row = self.con.execute(query).fetchone()
        if row is not None:
            (summary,) = row
        return 0 if summary is None else summary

    async def _async_update_summary(self, pdl, service, table):
        """Set summary."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        last_date = sum_value = summary = max_date = None
        query = f"SELECT last_date, value FROM service_summary WHERE pdl == '{pdl}' AND service == '{service}';"
        row = self.con.execute(query).fetchone()
        if row is not None:
            last_date, sum_value = row
        last_date = today - timedelta(days=365) if last_date is None else last_date
        sum_value = 0 if sum_value is None else sum_value

        query = f"SELECT SUM(value), MAX(date) FROM {table} WHERE pdl == '{pdl}' AND date > '{last_date}' AND date <= '{today}'"
        row = self.con.execute(query).fetchone()
        if row is not None:
            (summary, max_date) = row
        max_date = yesterday.strftime("%Y-%m-%d") if max_date is None else max_date
        sum_value = int(sum_value) if summary is None else int(sum_value) + int(summary)

        _LOGGER.debug(
            f"Insert or Update summary {service} at {max_date} with {sum_value}"
        )
        query = "INSERT OR REPLACE INTO service_summary VALUES (?, ?, ?, ?)"
        self.con.execute(query, [pdl, service, sum_value, max_date])

    async def _async_update_contracts(self, pdl, contracts):
        """Update contracts."""
        _LOGGER.debug("Insert or Update contracts")
        query = "INSERT OR REPLACE INTO contracts VALUES (?,?)"
        self.con.execute(query, [pdl, json.dumps(contracts)])

    async def _async_update_addresses(self, pdl, addresses):
        """Update addresses."""
        _LOGGER.debug("Insert or Update addresses")
        query = "INSERT OR REPLACE INTO addresses VALUES (?,?)"
        self.con.execute(query, [pdl, json.dumps(addresses)])

    async def _async_update_measurements(self, service, measurements, detail=False):
        """Update power."""
        _LOGGER.debug(f"Call update {service} , detail is {detail}")
        upi = None
        table = PRODUCTION if service == "production" else CONSUMPTION
        if detail:
            table = PRODUCTION_DETAIL if service == "production" else CONSUMPTION_DETAIL

        if (meter_reading := measurements.get("meter_reading")) and (
            interval_reading := measurements.get("meter_reading").get(
                "interval_reading"
            )
        ):
            upi = meter_reading.get("usage_point_id")
            if detail:
                config_query = f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?, ?, ?)"
                for interval in interval_reading:
                    interval_length = re.findall(
                        r"PT([0-9]+)M", interval.get("interval_length")
                    )[0]
                    self.con.execute(
                        config_query,
                        [
                            upi,
                            interval.get("date"),
                            interval.get("value"),
                            interval_length,
                            interval.get("measure_type"),
                        ],
                    )
            else:
                config_query = f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?)"
                for interval in interval_reading:
                    self.con.execute(
                        config_query, [upi, interval.get("date"), interval.get("value")]
                    )

        """Update summary table."""
        pdl = upi or self.pdl
        await self._async_update_summary(pdl, service, table)

    async def async_update(
        self,
        consumption=(False, False),
        production=(False, False),
    ):
        """Update database."""
        start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")

        if consumption[0]:
            _LOGGER.debug(f"Update consumption from {start} to {end}")
            try:
                measurements = await self.api.async_get_datas("consumption", start, end)
                await self._async_update_measurements("consumption", measurements)
                if consumption[1]:
                    start = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
                    _LOGGER.debug(f"Update detail consumption from {start} to {end})")
                    msrmts = await self.api.async_get_datas(
                        "consumption", start, end, True
                    )
                    await self._async_update_measurements("consumption", msrmts, True)
            except EnedisGatewayException:
                pass

        if production[0]:
            _LOGGER.debug(f"Update production from {start} to {end}")
            try:
                measurements = await self.api.async_get_datas("production", start, end)
                await self._async_update_measurements("production", measurements)
                if production[1]:
                    start = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
                    _LOGGER.debug(f"Update detail production from {start} to {end})")
                    msrmts = await self.api.async_get_datas(
                        "production", start, end, True
                    )
                    await self._async_update_measurements("production", msrmts, True)

            except EnedisGatewayException:
                pass

        """Fetch datas."""
        try:
            return await self.async_get_information_by_pdl(
                self.pdl, consumption, production
            )
        except EnedisGatewayException:
            pass
        except EnedisDatabaseException as error:
            raise EnedisException(error)


class EnedisException(Exception):
    """Enedis exception."""


class EnedisGatewayException(EnedisException):
    """Enedis exception."""

    def __init__(self, message):
        """Init."""
        self.message = message
        super().__init__(self.message)
        _LOGGER.error(message)


class EnedisDatabaseException(EnedisException):
    """Enedis database exception."""
