"""Config flow for the Midea CCM18 Modbus gateway."""

import logging
from typing import Any, override

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
import probatio

from .api import CCM18, CCM18Error
from .const import (
    CONF_DEVICE_ID,
    DEFAULT_DEVICE_ID,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): str,
        probatio.Optional(CONF_PORT, default=DEFAULT_PORT): probatio.Port(),
        probatio.Optional(CONF_DEVICE_ID, default=DEFAULT_DEVICE_ID): probatio.All(
            NumberSelector(
                NumberSelectorConfig(
                    min=1, max=247, step=1, mode=NumberSelectorMode.BOX
                )
            ),
            probatio.Coerce(int),
        ),
    }
)


class CCM18ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Midea CCM18 gateway."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            api = CCM18(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_DEVICE_ID],
                DEFAULT_TIMEOUT,
            )
            try:
                if not await api.async_get_online_units():
                    errors["base"] = "no_units"
            except CCM18Error:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            finally:
                await api.close()

            if not errors:
                return self.async_create_entry(
                    title=f"CCM18 {user_input[CONF_HOST]}", data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )
