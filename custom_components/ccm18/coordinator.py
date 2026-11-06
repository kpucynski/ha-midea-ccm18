"""Data update coordinator for the Midea CCM18 integration."""

import dataclasses
import datetime as dt
import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CCM18,
    POWER_ON,
    AuxFunction,
    CCM18Error,
    CCM18IndoorUnit,
    FanSpeed,
    Mode,
)
from .const import CONF_DEVICE_ID, DEFAULT_INTERVAL, DEFAULT_TIMEOUT, DOMAIN

_LOGGER = logging.getLogger(__name__)

type CCM18ConfigEntry = ConfigEntry[CCM18Coordinator]


class CCM18Coordinator(DataUpdateCoordinator[dict[int, CCM18IndoorUnit]]):
    """Poll all indoor units connected to a CCM18 gateway."""

    config_entry: CCM18ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: CCM18ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.data[CONF_HOST],
            update_interval=dt.timedelta(seconds=DEFAULT_INTERVAL),
        )
        self.host: str = entry.data[CONF_HOST]
        self.api = CCM18(
            self.host,
            entry.data[CONF_PORT],
            entry.data[CONF_DEVICE_ID],
            DEFAULT_TIMEOUT,
        )
        self._last_mode: dict[int, Mode] = {}
        self.gateway_device_id: str | None = None

    @override
    async def _async_update_data(self) -> dict[int, CCM18IndoorUnit]:
        try:
            units = await self.api.async_get_units()
        except CCM18Error as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"host": self.host, "error": str(err)},
            ) from err
        for index, unit in units.items():
            if (mode := unit.mode) is not None:
                self._last_mode[index] = mode
        return units

    @override
    async def async_shutdown(self) -> None:
        """Close the Modbus connection."""
        await super().async_shutdown()
        await self.api.close()

    def last_mode(self, index: int) -> Mode:
        """Return the last operating mode seen for a unit."""
        return self._last_mode.get(index, Mode.AUTO)

    def _apply(self, index: int, **changes: int) -> None:
        # The gateway takes a while to report new values, so update optimistically.
        if (unit := self.data.get(index)) is not None:
            self.data[index] = dataclasses.replace(unit, **changes)
            self.async_update_listeners()

    async def async_set_mode(self, index: int, mode: Mode, power_on: bool) -> None:
        """Set mode and power state of a unit."""
        try:
            await self.api.async_set_mode(index, mode, power_on)
        except CCM18Error as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_failed"
            ) from err
        self._last_mode[index] = mode
        self._apply(index, mode_octet=int(mode) | (POWER_ON if power_on else 0))

    async def async_set_fan_speed(self, index: int, fan_speed: FanSpeed) -> None:
        """Set fan speed of a unit."""
        try:
            await self.api.async_set_fan_speed(index, fan_speed)
        except CCM18Error as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_failed"
            ) from err
        self._apply(index, fan_octet=int(fan_speed))

    async def async_set_setpoint(self, index: int, temperature: int) -> None:
        """Set target temperature of a unit."""
        try:
            await self.api.async_set_setpoint(index, temperature)
        except CCM18Error as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_failed"
            ) from err
        self._apply(index, setpoint=temperature)

    async def async_set_aux_functions(self, index: int, functions: AuxFunction) -> None:
        """Set auxiliary functions of a unit."""
        try:
            await self.api.async_set_aux_functions(index, functions)
        except CCM18Error as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_failed"
            ) from err
        self._apply(index, aux_octet=int(functions))
