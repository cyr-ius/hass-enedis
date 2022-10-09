"""Config flow to configure integration."""
import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from enedisgatewaypy import EnedisByPDL, EnedisException
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_TOKEN
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_CONSUMTPION,
    CONF_PDL,
    CONF_PRODUCTION,
    CONF_RULE_DELETE,
    CONF_RULE_END_TIME,
    CONF_RULE_ID,
    CONF_RULE_NAME,
    CONF_RULE_NEW_ID,
    CONF_RULE_PRICE,
    CONF_RULE_START_TIME,
    CONF_RULES,
    CONSUMPTION_DAILY,
    CONSUMPTION_DETAIL,
    COST_CONSUMTPION,
    COST_OFFPEAK,
    COST_PEAK,
    COST_PRODUCTION,
    DEFAULT_CC_PRICE,
    DEFAULT_HC_PRICE,
    DEFAULT_HP_PRICE,
    DEFAULT_PC_PRICE,
    DOMAIN,
    PRODUCTION_DAILY,
    PRODUCTION_DETAIL,
)

PRODUCTION_CHOICE = [
    SelectOptionDict(value=PRODUCTION_DAILY, label="Journalier"),
    SelectOptionDict(value=PRODUCTION_DETAIL, label="Détaillé"),
]

CONSUMPTION_CHOICE = [
    SelectOptionDict(value=CONSUMPTION_DAILY, label="Journalier"),
    SelectOptionDict(value=CONSUMPTION_DETAIL, label="Détaillé"),
]

PRICE_CHOICE = [
    SelectOptionDict(value=f"{DEFAULT_HC_PRICE}", label="Tarif heure creuse"),
    SelectOptionDict(value=f"{DEFAULT_HP_PRICE}", label="Tarif heure pleine"),
    SelectOptionDict(value=f"{DEFAULT_CC_PRICE}", label="Tarif de base"),
    SelectOptionDict(value=f"{DEFAULT_PC_PRICE}", label="Tarif en rachat"),
]

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PDL): str,
        vol.Required(CONF_TOKEN): str,
        vol.Optional(
            CONF_CONSUMTPION, description={"suggested_value": CONSUMPTION_DAILY}
        ): SelectSelector(
            SelectSelectorConfig(
                options=CONSUMPTION_CHOICE,
                mode=SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        ),
        vol.Optional(CONF_PRODUCTION): SelectSelector(
            SelectSelectorConfig(
                options=PRODUCTION_CHOICE,
                mode=SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        ),
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
                return self.async_create_entry(
                    title=f"Linky ({user_input[CONF_PDL]})",
                    data=user_input,
                    options={
                        CONF_CONSUMTPION: user_input.get(CONF_CONSUMTPION),
                        COST_CONSUMTPION: DEFAULT_CC_PRICE,
                        CONF_PRODUCTION: user_input.get(CONF_PRODUCTION),
                        COST_PRODUCTION: DEFAULT_PC_PRICE,
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )


class EnedisOptionsFlowHandler(OptionsFlow):
    """Handle option."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        rules = config_entry.options.get(CONF_RULES, {})
        self._rules: dict[str, Any] = rules.copy()
        self._conf_rule_id: int | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        if user_input is not None:
            if sel_rule := user_input.get(CONF_RULES):
                return await self.async_step_rules(None, sel_rule)
            return self._save_config(user_input)

        return self._async_init_form()

    @callback
    def _save_config(self, data: dict[str, Any]) -> FlowResult:
        """Save the updated options."""
        new_data = {k: v for k, v in data.items() if k not in [CONF_RULES]}
        if self._rules:
            new_data[CONF_RULES] = self._rules

        return self.async_create_entry(title="", data=new_data)

    @callback
    def _async_init_form(self) -> FlowResult:
        """Handle a flow initialized by the user."""
        rules_list = {
            k: f"{v.get(CONF_RULE_NAME)} {v.get(CONF_RULE_START_TIME)}-{v.get(CONF_RULE_END_TIME)} {v.get(CONF_RULE_PRICE)}"
            if v
            else k
            for k, v in self._rules.items()
        }
        rules = {CONF_RULE_NEW_ID: "Add new", **rules_list}
        options = self.config_entry.options

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PRODUCTION,
                    description={"suggested_value": options.get(CONF_PRODUCTION)},
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=PRODUCTION_CHOICE,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                vol.Optional(
                    COST_PRODUCTION,
                    default=options.get(COST_PRODUCTION, DEFAULT_PC_PRICE),
                ): cv.positive_float,
                vol.Optional(
                    CONF_CONSUMTPION,
                    description={"suggested_value": options.get(CONF_CONSUMTPION)},
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=CONSUMPTION_CHOICE,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                vol.Optional(
                    COST_CONSUMTPION,
                    default=options.get(COST_CONSUMTPION, DEFAULT_CC_PRICE),
                ): cv.positive_float,
                vol.Optional(CONF_RULES): vol.In(rules),
                vol.Optional(
                    COST_PEAK, default=options.get(COST_PEAK, DEFAULT_HP_PRICE)
                ): cv.positive_float,
                vol.Optional(
                    COST_OFFPEAK, default=options.get(COST_OFFPEAK, DEFAULT_HC_PRICE)
                ): cv.positive_float,
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)

    async def async_step_rules(
        self, user_input: dict[str, Any] | None = None, rule_id: str | None = None
    ) -> FlowResult:
        """Handle options flow for apps list."""
        if rule_id is not None:
            self._conf_rule_id = rule_id if rule_id != CONF_RULE_NEW_ID else None
            return self._async_rules_form(rule_id)

        if user_input is not None:
            rule_id = user_input.get(CONF_RULE_ID, self._conf_rule_id)
            if rule_id:
                if user_input.get(CONF_RULE_DELETE, False):
                    self._rules.pop(rule_id)
                else:
                    self._rules[rule_id] = {
                        CONF_RULE_NAME: user_input.get(CONF_RULE_NAME),
                        CONF_RULE_START_TIME: user_input.get(CONF_RULE_START_TIME),
                        CONF_RULE_END_TIME: user_input.get(CONF_RULE_END_TIME),
                        CONF_RULE_PRICE: float(
                            user_input.get(CONF_RULE_PRICE, DEFAULT_CC_PRICE)
                        ),
                    }

        return await self.async_step_init()

    @callback
    def _async_rules_form(self, rule_id: str) -> FlowResult:
        """Return configuration form for rules."""
        if isinstance(
            (
                price := self._rules.get(rule_id, {}).get(
                    CONF_RULE_PRICE, "Tarif de base"
                )
            ),
            float,
        ):
            price = str(price)

        rule_schema = {
            vol.Optional(
                CONF_RULE_NAME,
                description={
                    "suggested_value": self._rules.get(rule_id, {}).get(CONF_RULE_NAME)
                },
            ): str,
            vol.Optional(
                CONF_RULE_START_TIME,
                description={
                    "suggested_value": self._rules.get(rule_id, {}).get(
                        CONF_RULE_START_TIME, "01H00"
                    )
                },
            ): str,
            vol.Optional(
                CONF_RULE_END_TIME,
                description={
                    "suggested_value": self._rules.get(rule_id, {}).get(
                        CONF_RULE_END_TIME, "06H00"
                    )
                },
            ): str,
            vol.Optional(
                CONF_RULE_PRICE,
                description={"suggested_value": price},
            ): SelectSelector(
                SelectSelectorConfig(
                    options=PRICE_CHOICE,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
        }
        if rule_id == CONF_RULE_NEW_ID:
            id = str(len(self._rules.keys()) + 1)
            data_schema = vol.Schema({vol.Required(CONF_RULE_ID): id, **rule_schema})
        else:
            data_schema = vol.Schema(
                {**rule_schema, vol.Optional(CONF_RULE_DELETE, default=False): bool}
            )

        return self.async_show_form(
            step_id="rules",
            data_schema=data_schema,
            description_placeholders={
                "rule_id": f"`{rule_id}`" if rule_id != CONF_RULE_NEW_ID else "",
            },
        )
