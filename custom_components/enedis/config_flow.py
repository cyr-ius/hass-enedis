"""Config flow to configure Heatzy."""
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_TOKEN
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    CONF_CONSUMPTION,
    CONF_CONSUMPTION_DETAIL,
    CONF_PDL,
    CONF_PRODUCTION,
    CONF_PRODUCTION_DETAIL,
    DOMAIN,
)
from .enedisgateway import EnedisException, EnedisGateway

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
        options = {CONF_CONSUMPTION: True}
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
            except EnedisException:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )


class EnedisOptionsFlowHandler(OptionsFlow):
    """Handle option."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CONSUMPTION,
                    default=self.config_entry.options.get(CONF_CONSUMPTION, True),
                ): bool,
                vol.Optional(
                    CONF_CONSUMPTION_DETAIL,
                    default=self.config_entry.options.get(CONF_CONSUMPTION_DETAIL, False),
                ): bool,
                vol.Optional(
                    CONF_PRODUCTION,
                    default=self.config_entry.options.get(CONF_PRODUCTION, False),
                ): bool,
                vol.Optional(
                    CONF_PRODUCTION_DETAIL,
                    default=self.config_entry.options.get(CONF_PRODUCTION_DETAIL, False),
                ): bool,
            },
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)
