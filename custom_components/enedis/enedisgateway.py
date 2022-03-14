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
            raise EnedisException("Request failed") from error

    async def async_get_identity(self):
        """Get identity."""
        payload = {"type": "identity", "usage_point_id": str(self.pdl)}
        return await self._async_make_request(payload)

    async def async_get_addresses(self):
        """Get addresses."""
        payload = {"type": "addresses", "usage_point_id": str(self.pdl)}
        return await self._async_make_request(payload)

    async def async_get_addresses_by_pdl(self):
        """Return all."""
        datas = {}
        addresses = await self.async_get_addresses()
        for addresses in addresses.get("customer", {}).get("usage_points"):
            if addresses.get("usage_point", {}).get("usage_point_id") == self.pdl:
                datas.update(addresses.get("usage_point"))
        return datas

    async def async_get_contracts(self):
        """Get contracts."""
        payload = {"type": "contracts", "usage_point_id": str(self.pdl)}
        return await self._async_make_request(payload)

    async def async_get_contract_by_pdl(self):
        """Return all."""
        datas = {}
        contracts = await self.async_get_contracts()
        for contract in contracts.get("customer", {}).get("usage_points"):
            if contract.get("usage_point", {}).get("usage_point_id") == self.pdl:
                datas.update(contract.get("contracts"))
        return datas

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

class EnedisException(Exception):
    """Enedis exception."""

class EnedisGatewayException(EnedisException):
    """Enedis gateway error."""

    def __init__(self, message):
        super(self,message)
        _LOGGER.error(message)