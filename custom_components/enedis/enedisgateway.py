"""Class for Enedis Gateway (http://enedisgateway.tech)."""


import logging
import re
import datetime
from datetime import datetime as dt

import requests
from requests.exceptions import RequestException

URL = "https://enedisgateway.tech"
API_URL = f"{URL}/api"
MANUFACTURER = "Enedis"
PRODUCTION = "Production"
PRODUCTION_DAILY = "production_daily"
PRODUCTION_DETAIL = "production_detail"
CONSUMPTION = "Consumption"
CONSUMPTION_DAILY = "consumption_daily"
CONSUMPTION_DETAIL = "consumption_detail"
HP = "peak_hours"
HC = "offpeak_hours"
DEFAULT_HP_PRICE = 0.1841
DEFAULT_HC_PRICE = 0.1470

_LOGGER = logging.getLogger(__name__)


class EnedisGateway:
    """Class for Enedis Gateway API."""

    def __init__(self, pdl, token, session=None):
        """Init."""
        self.pdl = str(pdl)
        self.token = token
        self.session = session if session else requests.Session()
        self.has_offpeak = False
        self.offpeaks = []

    async def _async_make_request(self, payload):
        """Request session."""
        headers = {"Authorization": self.token, "Content-Type": "application/json"}
        try:
            _LOGGER.debug(f"Make request {payload}")
            resp = await self.session.request(
                method="POST", url=API_URL, json=payload, headers=headers, timeout=5
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

    def hass_offpeak(self):
        """Has offpeak hours."""
        return len(self.offpeak) > 0

    def check_offpeak(self, start: datetime):
        """Return offpeak status."""
        if self.hass_offpeak:
            start_time = start.time()
            for range in self.offpeaks:
                starting = dt.strptime(range[0], "%HH%M").time()
                ending = dt.strptime(range[1], "%HH%M").time()
                if start_time > starting and start_time <= ending:
                    return True
        return False

    def get_offpeak(self):
        """Return offpeak detail."""
        return self.offpeaks

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
        for contract in contracts.get("customer", {}).get("usage_points", ""):
            if contract.get("usage_point", {}).get("usage_point_id") == self.pdl:
                datas.update(contract.get("contracts"))

        if offpeak_hours := datas.get("offpeak_hours"):
            self.offpeaks = re.findall("(?:(\\w+)-(\\w+))+", offpeak_hours)
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
        """Initialize."""
        super().__init__(message)
        _LOGGER.error(message)
