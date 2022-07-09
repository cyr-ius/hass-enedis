"""Config flow to configure integration."""
import logging

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_TOKEN, CONF_SOURCE
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import CONF_PDL, DOMAIN, COORDINATOR, CONF_DETAIL
from .enedisgateway import (
    EnedisGateway,
    EnedisGatewayException,
    HP,
    HC,
    DEFAULT_HC_PRICE,
    DEFAULT_HP_PRICE,
    CONSUMPTION,
    PRODUCTION,
)

DATA_SCHEMA = vol.Schema({vol.Required(CONF_PDL): str, vol.Required(CONF_TOKEN): str})

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
        options = {
            CONF_SOURCE: CONSUMPTION,
            HP: DEFAULT_HP_PRICE,
            CONF_DETAIL: False
        }
        if user_input is not None:
            try:
                await self.async_set_unique_id(user_input[CONF_PDL])
                self._abort_if_unique_id_configured()
                api = EnedisGateway(
                    pdl=user_input[CONF_PDL],
                    token=user_input[CONF_TOKEN],
                    session=async_create_clientsession(self.hass),
                )
                await api.async_get_identity()
                return self.async_create_entry(
                    title=DOMAIN, data=user_input, options=options
                )
            except EnedisGatewayException:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )


class EnedisOptionsFlowHandler(OptionsFlow):
    """Handle option."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.init_input = None
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:
            if (
                self.hass.data[DOMAIN][self.config_entry.entry_id][COORDINATOR]
                .data["contracts"]
                .get("offpeak_hours")
                is not None
            ):
                self.init_input = user_input
                return await self.async_step_offpeak()
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SOURCE,
                    default=self.config_entry.options.get(CONF_SOURCE, CONSUMPTION),
                ): vol.In([CONSUMPTION, PRODUCTION]),
                vol.Optional(
                    CONF_DETAIL,
                    default=self.config_entry.options.get(CONF_DETAIL),
                ): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)

    async def async_step_offpeak(self, user_input=None):
        """Handle a flow offpeak."""
        if user_input is not None:
            self.init_input.update(user_input)
            return self.async_create_entry(title="", data=self.init_input)

        offpeak_schema = vol.Schema(
            {
                vol.Optional(
                    HC, default=self.config_entry.options.get(HC, DEFAULT_HC_PRICE)
                ): cv.positive_float,
                vol.Optional(
                    HP, default=self.config_entry.options.get(HP, DEFAULT_HP_PRICE)
                ): cv.positive_float,
            }
        )
        return self.async_show_form(step_id="offpeak", data_schema=offpeak_schema)
