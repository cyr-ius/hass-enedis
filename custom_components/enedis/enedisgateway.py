"""Class for Enedis Gateway (http://enedisgateway.tech)."""


import logging
import re
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
        self.offpeak = []

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

    def has_offpeak(self):
        """Return offpeak status."""
        return self.has_offpeak

    def get_offpeak(self):
        """Return offpeak detail."""
        return self.offpeak

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
        # return await self._async_make_request(payload)
        return {
            "customer": {
                "customer_id": "-1137954749",
                "usage_points": [
                    {
                        "usage_point": {
                            "usage_point_id": "09171201102829",
                            "usage_point_status": "com",
                            "meter_type": "AMM",
                        },
                        "contracts": {
                            "segment": "C5",
                            "subscribed_power": "9 kVA",
                            "distribution_tariff": "BTINFMUDT",
                            "last_activation_date": "2006-05-24+02:00",
                            "offpeak_hours": "HC (1H30-8H00;12H30-14H00)",
                            "contract_type": "Contrat Protocole501",
                            "contract_status": "SERVC",
                            "last_distribution_tariff_change_date": "2019-09-13+02:00",
                        },
                    }
                ],
            }
        }

    async def async_get_contract_by_pdl(self):
        """Return all."""
        datas = {}
        contracts = await self.async_get_contracts()
        for contract in contracts.get("customer", {}).get("usage_points"):
            if contract.get("usage_point", {}).get("usage_point_id") == self.pdl:
                datas.update(contract.get("contracts"))

        if offpeak_hours := datas.get("offpeak_hours"):
            rslt = re.findall("HC \\((.*)\\)", offpeak_hours)
            if len(rslt) == 1:
                self.has_offpeak = True
                for ranges in rslt[0].split(";"):
                    start, end = ranges.split("-")
                    self.offpeak.append((start, end))
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

        # return await self._async_make_request(payload)
        return {
            "meter_reading": {
                "interval_reading": [
                    {"value": "42382", "date": "2022-02-16"},
                    {"value": "48288", "date": "2022-02-17"},
                    {"value": "56183", "date": "2022-02-18"},
                    {"value": "76946", "date": "2022-02-19"},
                    {"value": "48110", "date": "2022-02-20"},
                    {"value": "48987", "date": "2022-02-21"},
                    {"value": "64805", "date": "2022-02-22"},
                    {"value": "62343", "date": "2022-02-23"},
                    {"value": "46195", "date": "2022-02-24"},
                    {"value": "79980", "date": "2022-02-25"},
                    {"value": "69647", "date": "2022-02-26"},
                    {"value": "43207", "date": "2022-02-27"},
                    {"value": "37897", "date": "2022-02-28"},
                    {"value": "27130", "date": "2022-03-01"},
                    {"value": "28100", "date": "2022-03-02"},
                    {"value": "53347", "date": "2022-03-03"},
                    {"value": "71037", "date": "2022-03-04"},
                    {"value": "67195", "date": "2022-03-05"},
                    {"value": "37867", "date": "2022-03-06"},
                    {"value": "57893", "date": "2022-03-07"},
                    {"value": "42045", "date": "2022-03-08"},
                    {"value": "32464", "date": "2022-03-09"},
                    {"value": "38336", "date": "2022-03-10"},
                    {"value": "62200", "date": "2022-03-11"},
                    {"value": "67007", "date": "2022-03-12"},
                    {"value": "66275", "date": "2022-03-13"},
                    {
                        "value": "918",
                        "date": "2022-03-14 00:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "366",
                        "date": "2022-03-14 01:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "340",
                        "date": "2022-03-14 01:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2318",
                        "date": "2022-03-14 02:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3724",
                        "date": "2022-03-14 02:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3044",
                        "date": "2022-03-14 03:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3150",
                        "date": "2022-03-14 03:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5098",
                        "date": "2022-03-14 04:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4186",
                        "date": "2022-03-14 04:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4498",
                        "date": "2022-03-14 05:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5754",
                        "date": "2022-03-14 05:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "6832",
                        "date": "2022-03-14 06:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "8226",
                        "date": "2022-03-14 06:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "6770",
                        "date": "2022-03-14 07:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4744",
                        "date": "2022-03-14 07:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5444",
                        "date": "2022-03-14 08:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "7250",
                        "date": "2022-03-14 08:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4816",
                        "date": "2022-03-14 09:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3162",
                        "date": "2022-03-14 09:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1642",
                        "date": "2022-03-14 10:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "718",
                        "date": "2022-03-14 10:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1452",
                        "date": "2022-03-14 11:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1360",
                        "date": "2022-03-14 11:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1684",
                        "date": "2022-03-14 12:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3586",
                        "date": "2022-03-14 12:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3624",
                        "date": "2022-03-14 13:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1612",
                        "date": "2022-03-14 13:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "508",
                        "date": "2022-03-14 14:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "482",
                        "date": "2022-03-14 14:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "522",
                        "date": "2022-03-14 15:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2060",
                        "date": "2022-03-14 15:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2064",
                        "date": "2022-03-14 16:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1470",
                        "date": "2022-03-14 16:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "466",
                        "date": "2022-03-14 17:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4162",
                        "date": "2022-03-14 17:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4510",
                        "date": "2022-03-14 18:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5976",
                        "date": "2022-03-14 18:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5546",
                        "date": "2022-03-14 19:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5002",
                        "date": "2022-03-14 19:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3688",
                        "date": "2022-03-14 20:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2460",
                        "date": "2022-03-14 20:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "506",
                        "date": "2022-03-14 21:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1334",
                        "date": "2022-03-14 21:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2314",
                        "date": "2022-03-14 22:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2572",
                        "date": "2022-03-14 22:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1846",
                        "date": "2022-03-14 23:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "472",
                        "date": "2022-03-14 23:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "414",
                        "date": "2022-03-15 00:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "720",
                        "date": "2022-03-15 00:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2096",
                        "date": "2022-03-15 01:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2080",
                        "date": "2022-03-15 01:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2310",
                        "date": "2022-03-15 02:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "828",
                        "date": "2022-03-15 02:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "778",
                        "date": "2022-03-15 03:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "296",
                        "date": "2022-03-15 03:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1938",
                        "date": "2022-03-15 04:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1998",
                        "date": "2022-03-15 04:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2020",
                        "date": "2022-03-15 05:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "740",
                        "date": "2022-03-15 05:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2526",
                        "date": "2022-03-15 06:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "6278",
                        "date": "2022-03-15 06:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5354",
                        "date": "2022-03-15 07:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5236",
                        "date": "2022-03-15 07:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "6222",
                        "date": "2022-03-15 08:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5062",
                        "date": "2022-03-15 08:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2344",
                        "date": "2022-03-15 09:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "354",
                        "date": "2022-03-15 09:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "410",
                        "date": "2022-03-15 10:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2012",
                        "date": "2022-03-15 10:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2024",
                        "date": "2022-03-15 11:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1732",
                        "date": "2022-03-15 11:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "316",
                        "date": "2022-03-15 12:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "296",
                        "date": "2022-03-15 12:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "742",
                        "date": "2022-03-15 13:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1402",
                        "date": "2022-03-15 13:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2552",
                        "date": "2022-03-15 14:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2386",
                        "date": "2022-03-15 14:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "672",
                        "date": "2022-03-15 15:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "282",
                        "date": "2022-03-15 15:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "316",
                        "date": "2022-03-15 16:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "276",
                        "date": "2022-03-15 16:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1292",
                        "date": "2022-03-15 17:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2200",
                        "date": "2022-03-15 17:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2220",
                        "date": "2022-03-15 18:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "514",
                        "date": "2022-03-15 18:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "502",
                        "date": "2022-03-15 19:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "688",
                        "date": "2022-03-15 19:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1214",
                        "date": "2022-03-15 20:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2366",
                        "date": "2022-03-15 20:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2252",
                        "date": "2022-03-15 21:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1376",
                        "date": "2022-03-15 21:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "402",
                        "date": "2022-03-15 22:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1004",
                        "date": "2022-03-15 22:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "444",
                        "date": "2022-03-15 23:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2158",
                        "date": "2022-03-15 23:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2158",
                        "date": "2022-03-16 00:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2000",
                        "date": "2022-03-16 00:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "368",
                        "date": "2022-03-16 01:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "296",
                        "date": "2022-03-16 01:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "784",
                        "date": "2022-03-16 02:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2118",
                        "date": "2022-03-16 02:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4030",
                        "date": "2022-03-16 03:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3006",
                        "date": "2022-03-16 03:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1838",
                        "date": "2022-03-16 04:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1030",
                        "date": "2022-03-16 04:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "454",
                        "date": "2022-03-16 05:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1104",
                        "date": "2022-03-16 05:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1992",
                        "date": "2022-03-16 06:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5752",
                        "date": "2022-03-16 06:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4368",
                        "date": "2022-03-16 07:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2804",
                        "date": "2022-03-16 07:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3810",
                        "date": "2022-03-16 08:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3072",
                        "date": "2022-03-16 08:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3324",
                        "date": "2022-03-16 09:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2116",
                        "date": "2022-03-16 09:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2802",
                        "date": "2022-03-16 10:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1056",
                        "date": "2022-03-16 10:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "366",
                        "date": "2022-03-16 11:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "390",
                        "date": "2022-03-16 11:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "516",
                        "date": "2022-03-16 12:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2084",
                        "date": "2022-03-16 12:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2546",
                        "date": "2022-03-16 13:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1716",
                        "date": "2022-03-16 13:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "478",
                        "date": "2022-03-16 14:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "364",
                        "date": "2022-03-16 14:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "508",
                        "date": "2022-03-16 15:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1360",
                        "date": "2022-03-16 15:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2380",
                        "date": "2022-03-16 16:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2230",
                        "date": "2022-03-16 16:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "690",
                        "date": "2022-03-16 17:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4742",
                        "date": "2022-03-16 17:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4112",
                        "date": "2022-03-16 18:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4294",
                        "date": "2022-03-16 18:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4706",
                        "date": "2022-03-16 19:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3774",
                        "date": "2022-03-16 19:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2214",
                        "date": "2022-03-16 20:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "546",
                        "date": "2022-03-16 20:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "482",
                        "date": "2022-03-16 21:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "422",
                        "date": "2022-03-16 21:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1988",
                        "date": "2022-03-16 22:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2704",
                        "date": "2022-03-16 22:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2120",
                        "date": "2022-03-16 23:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "946",
                        "date": "2022-03-16 23:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "392",
                        "date": "2022-03-17 00:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "422",
                        "date": "2022-03-17 00:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1132",
                        "date": "2022-03-17 01:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1988",
                        "date": "2022-03-17 01:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2464",
                        "date": "2022-03-17 02:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2000",
                        "date": "2022-03-17 02:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "728",
                        "date": "2022-03-17 03:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "356",
                        "date": "2022-03-17 03:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "664",
                        "date": "2022-03-17 04:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2034",
                        "date": "2022-03-17 04:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2332",
                        "date": "2022-03-17 05:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2214",
                        "date": "2022-03-17 05:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2178",
                        "date": "2022-03-17 06:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5922",
                        "date": "2022-03-17 06:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4952",
                        "date": "2022-03-17 07:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5624",
                        "date": "2022-03-17 07:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5742",
                        "date": "2022-03-17 08:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "6400",
                        "date": "2022-03-17 08:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3766",
                        "date": "2022-03-17 09:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1090",
                        "date": "2022-03-17 09:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "954",
                        "date": "2022-03-17 10:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2110",
                        "date": "2022-03-17 10:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2934",
                        "date": "2022-03-17 11:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2712",
                        "date": "2022-03-17 11:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2150",
                        "date": "2022-03-17 12:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1274",
                        "date": "2022-03-17 12:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1732",
                        "date": "2022-03-17 13:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1824",
                        "date": "2022-03-17 13:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2194",
                        "date": "2022-03-17 14:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2688",
                        "date": "2022-03-17 14:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3148",
                        "date": "2022-03-17 15:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1518",
                        "date": "2022-03-17 15:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1246",
                        "date": "2022-03-17 16:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "564",
                        "date": "2022-03-17 16:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2242",
                        "date": "2022-03-17 17:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5800",
                        "date": "2022-03-17 17:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "6358",
                        "date": "2022-03-17 18:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1442",
                        "date": "2022-03-17 18:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1226",
                        "date": "2022-03-17 19:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1232",
                        "date": "2022-03-17 19:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2480",
                        "date": "2022-03-17 20:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2270",
                        "date": "2022-03-17 20:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2206",
                        "date": "2022-03-17 21:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1320",
                        "date": "2022-03-17 21:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "508",
                        "date": "2022-03-17 22:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "412",
                        "date": "2022-03-17 22:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1758",
                        "date": "2022-03-17 23:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2096",
                        "date": "2022-03-17 23:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2052",
                        "date": "2022-03-18 00:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1582",
                        "date": "2022-03-18 00:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "264",
                        "date": "2022-03-18 01:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "290",
                        "date": "2022-03-18 01:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1824",
                        "date": "2022-03-18 02:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2646",
                        "date": "2022-03-18 02:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3292",
                        "date": "2022-03-18 03:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2510",
                        "date": "2022-03-18 03:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2076",
                        "date": "2022-03-18 04:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1294",
                        "date": "2022-03-18 04:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1272",
                        "date": "2022-03-18 05:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4172",
                        "date": "2022-03-18 05:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4198",
                        "date": "2022-03-18 06:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "8086",
                        "date": "2022-03-18 06:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "6572",
                        "date": "2022-03-18 07:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5804",
                        "date": "2022-03-18 07:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "6564",
                        "date": "2022-03-18 08:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4680",
                        "date": "2022-03-18 08:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5088",
                        "date": "2022-03-18 09:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2132",
                        "date": "2022-03-18 09:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2900",
                        "date": "2022-03-18 10:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1438",
                        "date": "2022-03-18 10:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "860",
                        "date": "2022-03-18 11:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1582",
                        "date": "2022-03-18 11:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2214",
                        "date": "2022-03-18 12:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4472",
                        "date": "2022-03-18 12:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4604",
                        "date": "2022-03-18 13:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3156",
                        "date": "2022-03-18 13:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2012",
                        "date": "2022-03-18 14:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2180",
                        "date": "2022-03-18 14:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1630",
                        "date": "2022-03-18 15:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2948",
                        "date": "2022-03-18 15:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3038",
                        "date": "2022-03-18 16:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1282",
                        "date": "2022-03-18 16:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2022",
                        "date": "2022-03-18 17:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1384",
                        "date": "2022-03-18 17:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2976",
                        "date": "2022-03-18 18:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4854",
                        "date": "2022-03-18 18:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2838",
                        "date": "2022-03-18 19:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2648",
                        "date": "2022-03-18 19:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1466",
                        "date": "2022-03-18 20:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "764",
                        "date": "2022-03-18 20:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "864",
                        "date": "2022-03-18 21:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2158",
                        "date": "2022-03-18 21:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2126",
                        "date": "2022-03-18 22:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2056",
                        "date": "2022-03-18 22:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "376",
                        "date": "2022-03-18 23:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "416",
                        "date": "2022-03-18 23:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "532",
                        "date": "2022-03-19 00:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1978",
                        "date": "2022-03-19 00:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1976",
                        "date": "2022-03-19 01:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1990",
                        "date": "2022-03-19 01:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "770",
                        "date": "2022-03-19 02:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1112",
                        "date": "2022-03-19 02:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1814",
                        "date": "2022-03-19 03:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2576",
                        "date": "2022-03-19 03:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2274",
                        "date": "2022-03-19 04:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1992",
                        "date": "2022-03-19 04:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "356",
                        "date": "2022-03-19 05:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "396",
                        "date": "2022-03-19 05:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1558",
                        "date": "2022-03-19 06:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2840",
                        "date": "2022-03-19 06:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1970",
                        "date": "2022-03-19 07:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1988",
                        "date": "2022-03-19 07:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "988",
                        "date": "2022-03-19 08:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2246",
                        "date": "2022-03-19 08:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4898",
                        "date": "2022-03-19 09:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "6324",
                        "date": "2022-03-19 09:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "7220",
                        "date": "2022-03-19 10:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "5916",
                        "date": "2022-03-19 10:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4184",
                        "date": "2022-03-19 11:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3630",
                        "date": "2022-03-19 11:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2378",
                        "date": "2022-03-19 12:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2064",
                        "date": "2022-03-19 12:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2720",
                        "date": "2022-03-19 13:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3140",
                        "date": "2022-03-19 13:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1866",
                        "date": "2022-03-19 14:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "550",
                        "date": "2022-03-19 14:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1426",
                        "date": "2022-03-19 15:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "568",
                        "date": "2022-03-19 15:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4988",
                        "date": "2022-03-19 16:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "4532",
                        "date": "2022-03-19 16:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3934",
                        "date": "2022-03-19 17:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "538",
                        "date": "2022-03-19 17:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "466",
                        "date": "2022-03-19 18:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "670",
                        "date": "2022-03-19 18:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2156",
                        "date": "2022-03-19 19:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3386",
                        "date": "2022-03-19 19:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3134",
                        "date": "2022-03-19 20:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2894",
                        "date": "2022-03-19 20:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "3050",
                        "date": "2022-03-19 21:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "1524",
                        "date": "2022-03-19 21:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "2256",
                        "date": "2022-03-19 22:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "462",
                        "date": "2022-03-19 22:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "416",
                        "date": "2022-03-19 23:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "436",
                        "date": "2022-03-19 23:30:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                    {
                        "value": "412",
                        "date": "2022-03-20 00:00:00",
                        "interval_length": "PT30M",
                        "measure_type": "B",
                    },
                ],
                "reading_type": {
                    "unit": "W",
                    "measurement_kind": "power",
                    "aggregate": "average",
                },
            }
        }


class EnedisException(Exception):
    """Enedis exception."""


class EnedisGatewayException(EnedisException):
    """Enedis gateway error."""

    def __init__(self, message):
        """Initialize."""
        super().__init__(message)
        _LOGGER.error(message)
