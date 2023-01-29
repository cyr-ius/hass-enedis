"""Config flow to configure integration."""
from datetime import datetime as dt
import logging
from typing import Any

from myelectricaldatapy import EnedisByPDL, EnedisException
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_TOKEN
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_create_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TimeSelector,
    TimeSelectorConfig,
)

from .const import (
    AUTH,
    CONF_CONSUMPTION,
    CONF_ECOWATT,
    CONF_PDL,
    CONF_PRICE_NEW_ID,
    CONF_PRICING_COST,
    CONF_PRICING_DELETE,
    CONF_PRICING_ID,
    CONF_PRICING_INTERVALS,
    CONF_PRICING_NAME,
    CONF_PRICINGS,
    CONF_PRODUCTION,
    CONF_RULE_DELETE,
    CONF_RULE_END_TIME,
    CONF_RULE_ID,
    CONF_RULE_NEW_ID,
    CONF_RULE_START_TIME,
    CONF_RULES,
    CONF_SERVICE,
    CONF_TEMPO,
    CONSUMPTION,
    CONSUMPTION_DAILY,
    CONSUMPTION_DETAIL,
    DEFAULT_CC_PRICE,
    DEFAULT_CONSUMPTION,
    DEFAULT_PC_PRICE,
    DEFAULT_PRODUCTION,
    DEFAULT_CONSUMPTION_TEMPO,
    DOMAIN,
    PRODUCTION,
    PRODUCTION_DAILY,
    PRODUCTION_DETAIL,
    SAVE,
    CONF_AUTH,
)

PRODUCTION_CHOICE = [
    SelectOptionDict(value=PRODUCTION_DAILY, label="Journalier"),
    SelectOptionDict(value=PRODUCTION_DETAIL, label="Détaillé"),
]
CONSUMPTION_CHOICE = [
    SelectOptionDict(value=CONSUMPTION_DAILY, label="Journalier"),
    SelectOptionDict(value=CONSUMPTION_DETAIL, label="Détaillé"),
]


DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PDL): str,
        vol.Required(CONF_TOKEN): str,
        vol.Optional(CONF_ECOWATT): bool,
        vol.Optional(CONF_PRODUCTION): bool,
        vol.Optional(CONF_CONSUMPTION): bool,
        vol.Optional(CONF_TEMPO): bool,
    }
)

_LOGGER = logging.getLogger(__name__)


class EnedisFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a Enedis config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get option flow."""
        return EnedisOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        errors = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_PDL: user_input[CONF_PDL]})
            api = EnedisByPDL(
                token=user_input[CONF_TOKEN],
                session=async_create_clientsession(self.hass),
                timeout=30,
            )
            try:
                await api.async_get_identity(user_input[CONF_PDL])
            except EnedisException as error:
                _LOGGER.error(error)
                errors["base"] = "cannot_connect"
            else:
                options = {
                    CONF_AUTH: {CONF_TOKEN: user_input.get(CONF_TOKEN)},
                }
                if b_tempo := user_input[CONF_TEMPO]:
                    options.update({CONF_CONSUMPTION: {CONF_TEMPO: b_tempo}})
                if user_input[CONF_PRODUCTION]:
                    options.update({CONF_PRODUCTION: {CONF_SERVICE: PRODUCTION_DAILY}})
                if user_input[CONF_CONSUMPTION]:
                    options.update(
                        {CONF_CONSUMPTION: {CONF_SERVICE: CONSUMPTION_DAILY}}
                    )

                options = default_settings(options)
                return self.async_create_entry(
                    title=f"Linky ({user_input[CONF_PDL]})",
                    data=user_input,
                    options=options,
                )

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )


class EnedisOptionsFlowHandler(OptionsFlow):
    """Handle option."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        _auth: dict[str, Any] = config_entry.options.get("auth", {})
        _production: dict[str, Any] = config_entry.options.get(PRODUCTION, {})
        _consumption: dict[str, Any] = config_entry.options.get(CONSUMPTION, {})
        self._datas = {
            AUTH: _auth.copy(),
            PRODUCTION: _production.copy(),
            CONSUMPTION: _consumption.copy(),
        }
        self._conf_rule_id: int | None = None
        self._conf_pricing_id: int | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        return self.async_show_menu(
            step_id="init", menu_options=[AUTH, PRODUCTION, CONSUMPTION, SAVE]
        )

    async def async_step_authentication(self, user_input: dict[str, Any] | None = None):
        """Authentification step."""
        step_id = AUTH
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_TOKEN,
                    default=self._datas[step_id].get(
                        CONF_TOKEN, self.config_entry.data[CONF_TOKEN]
                    ),
                ): str,
                vol.Optional(
                    CONF_ECOWATT,
                    default=self._datas[step_id].get(CONF_ECOWATT, False),
                ): bool,
            }
        )
        if user_input is not None:
            self._datas[step_id].update(**user_input)
            return await self.async_step_init()
        return self.async_show_form(
            step_id=step_id, data_schema=schema, last_step=False
        )

    async def async_step_production(self, user_input: dict[str, Any] | None = None):
        """Production step."""
        step_id = PRODUCTION
        pricing = self._datas[step_id].get(CONF_PRICINGS, {})
        pricing_list = {
            pricing_id: f"{v.get(CONF_PRICING_NAME)} - {v.get(CONF_PRICING_COST)}"
            for pricing_id, v in pricing.items()
        }
        pricings = {CONF_PRICE_NEW_ID: "Add new pricing", **pricing_list}
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SERVICE,
                    description={
                        "suggested_value": self._datas[step_id].get(CONF_SERVICE)
                    },
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=PRODUCTION_CHOICE,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                vol.Optional(CONF_PRICINGS): vol.In(pricings),
            }
        )
        if user_input is not None:
            self._datas[step_id].update({CONF_SERVICE: user_input.get(CONF_SERVICE)})
            if sel_pricing := user_input.get(CONF_PRICINGS):
                return await self.async_step_pricings(None, sel_pricing, step_id)
            return await self.async_step_init()
        return self.async_show_form(
            step_id=step_id, data_schema=schema, last_step=False
        )

    async def async_step_consumption(self, user_input: dict[str, Any] | None = None):
        """Consumption step."""
        step_id = CONSUMPTION
        pricing = self._datas[step_id].get(CONF_PRICINGS, {})
        pricing_list = {
            pricing_id: f"{v.get(CONF_PRICING_NAME)} - {v.get(CONF_PRICING_COST)}"
            for pricing_id, v in pricing.items()
        }
        pricings = {CONF_PRICE_NEW_ID: "Add new pricing", **pricing_list}
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_TEMPO,
                    default=self._datas[step_id].get(CONF_TEMPO, False),
                ): bool,
                vol.Optional(
                    CONF_SERVICE,
                    description={
                        "suggested_value": self._datas[step_id].get(CONF_SERVICE)
                    },
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=CONSUMPTION_CHOICE,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                vol.Optional(CONF_PRICINGS): vol.In(pricings),
            }
        )
        if user_input is not None:
            self._datas[step_id].update({CONF_SERVICE: user_input.get(CONF_SERVICE)})
            self._datas[step_id].update({CONF_TEMPO: user_input[CONF_TEMPO]})
            if sel_pricing := user_input.get(CONF_PRICINGS):
                return await self.async_step_pricings(None, sel_pricing, step_id)
            return await self.async_step_init()
        return self.async_show_form(
            step_id=step_id, data_schema=schema, last_step=False
        )

    async def async_step_save(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult():
        """Save the updated options."""
        self._datas = default_settings(self._datas)
        self._datas.update({"last_update": dt.now()})

        return self.async_create_entry(title="", data=self._datas)

    async def async_step_pricings(
        self,
        user_input: dict[str, Any] | None = None,
        pricing_id: str | None = None,
        step_id: str | None = None,
    ) -> FlowResult:
        """Handle options flow for apps list."""
        if pricing_id is not None:
            self._conf_pricing_id = (
                pricing_id if pricing_id != CONF_PRICE_NEW_ID else None
            )
            return self._async_pricings_form(pricing_id, step_id)

        if user_input is not None:
            pricing_id = user_input.get(CONF_PRICING_ID, self._conf_pricing_id)
            step_id = user_input["step_id"]
            if pricing_id:
                pricings = self._datas[step_id].get(CONF_PRICINGS, {})
                if user_input.get(CONF_PRICING_DELETE, False):
                    pricings.pop(pricing_id)
                else:
                    intervals = pricings.get(pricing_id, {}).get(
                        CONF_PRICING_INTERVALS, {}
                    )
                    default_price = (
                        DEFAULT_CC_PRICE
                        if step_id == CONF_CONSUMPTION
                        else DEFAULT_PC_PRICE
                    )
                    pricings.update(
                        {
                            str(pricing_id): {
                                CONF_PRICING_NAME: user_input.get(CONF_PRICING_NAME),
                                CONF_PRICING_COST: float(
                                    user_input.get(CONF_PRICING_COST, default_price)
                                ),
                                CONF_PRICING_INTERVALS: intervals,
                            }
                        }
                    )

                    if self._datas[step_id].get(CONF_TEMPO):
                        pricings[pricing_id].update(
                            {
                                CONF_PRICING_COST: CONF_TEMPO,
                                "BLUE": user_input["BLUE"],
                                "WHITE": user_input["WHITE"],
                                "RED": user_input["RED"],
                            }
                        )

                    self._datas[step_id][CONF_PRICINGS].update(**pricings)

                    if rule_id := user_input.get(CONF_RULES):
                        return await self.async_step_rules(
                            rule_id=rule_id, pricing_id=pricing_id, step_id=step_id
                        )

        if step_id == CONSUMPTION:
            return await self.async_step_consumption()
        else:
            return await self.async_step_production()

    @callback
    def _async_pricings_form(self, pricing_id: str, step_id: str) -> FlowResult:
        """Return configuration form for rules."""
        _rules = (
            self._datas[step_id]
            .get(CONF_PRICINGS, {})
            .get(pricing_id, {})
            .get(CONF_PRICING_INTERVALS, {})
        )
        rules_list = {
            rule_id: f"{v.get(CONF_RULE_START_TIME)} - {v.get(CONF_RULE_END_TIME)}"
            for rule_id, v in _rules.items()
        }
        rules = {CONF_RULE_NEW_ID: "Add new", **rules_list}

        _datas = self._datas[step_id].get(CONF_PRICINGS, {})
        schema = {
            vol.Required("step_id"): step_id,
            vol.Optional(
                CONF_PRICING_NAME,
                description={
                    "suggested_value": _datas.get(pricing_id, {}).get(CONF_PRICING_NAME)
                },
            ): str,
            vol.Optional(
                CONF_PRICING_COST,
                description={
                    "suggested_value": _datas.get(pricing_id, {}).get(CONF_PRICING_COST)
                },
            ): cv.positive_float,
        }

        tempo_schema = {
            vol.Optional(
                "BLUE",
                description={"suggested_value": _datas.get(pricing_id, {}).get("BLUE")},
            ): cv.positive_float,
            vol.Optional(
                "WHITE",
                description={
                    "suggested_value": _datas.get(pricing_id, {}).get("WHITE")
                },
            ): cv.positive_float,
            vol.Optional(
                "RED",
                description={"suggested_value": _datas.get(pricing_id, {}).get("RED")},
            ): cv.positive_float,
        }

        if self._datas[step_id].get(CONF_TEMPO):
            schema.pop(CONF_PRICING_COST)
            schema.update(tempo_schema)

        schema.update({vol.Optional(CONF_RULES): vol.In(rules)})

        if pricing_id == CONF_PRICE_NEW_ID:
            id = int(max(_datas.keys())) + 1 if _datas.keys() else 1
            data_schema = vol.Schema({vol.Required(CONF_PRICING_ID): str(id), **schema})
        else:
            data_schema = vol.Schema(
                {**schema, vol.Optional(CONF_PRICING_DELETE, default=False): bool}
            )

        return self.async_show_form(
            step_id="pricings", data_schema=data_schema, last_step=False
        )

    async def async_step_rules(
        self,
        user_input: dict[str, Any] | None = None,
        rule_id: str | None = None,
        pricing_id: str | None = None,
        step_id: str | None = None,
    ) -> FlowResult:
        """Handle options flow for apps list."""
        if rule_id is not None:
            self._conf_rule_id = rule_id if rule_id != CONF_RULE_NEW_ID else None
            return self._async_rules_form(rule_id, pricing_id, step_id)

        if user_input is not None:
            rule_id = user_input.get(CONF_RULE_ID, self._conf_rule_id)
            step_id = user_input["step_id"]
            pricing_id = user_input[CONF_PRICING_ID]
            if rule_id:
                rules = self._datas[step_id][CONF_PRICINGS][pricing_id].get(
                    CONF_PRICING_INTERVALS, {}
                )
                if user_input.get(CONF_RULE_DELETE, False):
                    rules.pop(str(rule_id))
                else:
                    rules.update(
                        {
                            str(rule_id): {
                                CONF_RULE_START_TIME: user_input.get(
                                    CONF_RULE_START_TIME
                                ),
                                CONF_RULE_END_TIME: user_input.get(CONF_RULE_END_TIME),
                            }
                        }
                    )
                    self._datas[step_id][CONF_PRICINGS][pricing_id][
                        CONF_PRICING_INTERVALS
                    ].update(**rules)

            return await self.async_step_pricings(None, pricing_id, step_id)

    @callback
    def _async_rules_form(
        self, rule_id: str, pricing_id: str, step_id: str
    ) -> FlowResult:
        """Return configuration form for rules."""
        _datas = (
            self._datas.get(step_id, {})
            .get(CONF_PRICINGS, {})
            .get(pricing_id, {})
            .get(CONF_PRICING_INTERVALS)
        )

        schema = {
            vol.Required("step_id"): step_id,
            vol.Required(CONF_PRICING_ID): pricing_id,
            vol.Optional(
                CONF_RULE_START_TIME,
                description={
                    "suggested_value": _datas.get(rule_id, {}).get(CONF_RULE_START_TIME)
                },
            ): TimeSelector(TimeSelectorConfig()),
            vol.Optional(
                CONF_RULE_END_TIME,
                description={
                    "suggested_value": _datas.get(rule_id, {}).get(CONF_RULE_END_TIME)
                },
            ): TimeSelector(TimeSelectorConfig()),
        }
        if rule_id == CONF_RULE_NEW_ID:
            id = int(max(_datas.keys())) + 1 if _datas.keys() else 1
            data_schema = vol.Schema({vol.Required(CONF_RULE_ID): str(id), **schema})
        else:
            data_schema = vol.Schema(
                {**schema, vol.Optional(CONF_RULE_DELETE, default=False): bool}
            )

        return self.async_show_form(
            step_id="rules", data_schema=data_schema, last_step=False
        )


def default_settings(datas: dict[str, Any]):
    """Set default datas if missing."""
    production = datas.get(PRODUCTION)
    if production.get(CONF_SERVICE) and len(production.get(CONF_PRICINGS, {})) == 0:
        datas[PRODUCTION][CONF_PRICINGS] = DEFAULT_PRODUCTION

    consumption = datas.get(CONSUMPTION)
    if consumption.get(CONF_SERVICE) and len(consumption.get(CONF_PRICINGS, {})) == 0:
        datas[CONSUMPTION][CONF_PRICINGS] = DEFAULT_CONSUMPTION

    if consumption.get(CONF_TEMPO) and len(consumption.get(CONF_PRICINGS, {})) == 0:
        datas[CONSUMPTION] = {
            CONF_SERVICE: CONSUMPTION_DETAIL,
            CONF_TEMPO: consumption.get(CONF_TEMPO),
            CONF_PRICINGS: DEFAULT_CONSUMPTION_TEMPO,
        }

    return datas
