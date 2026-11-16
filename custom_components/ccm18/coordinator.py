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
    DEFAULT_SETPOINT,
    FAN_SPEED_MASK,
    POWER_ON,
    AuxFunction,
    CCM18Error,
    CCM18Status,
    FanSpeed,
    Mode,
)
from .const import CONF_DEVICE_ID, DEFAULT_INTERVAL, DEFAULT_TIMEOUT, DOMAIN

_LOGGER = logging.getLogger(__name__)

type CCM18ConfigEntry = ConfigEntry[CCM18Coordinator]


class CCM18Coordinator(DataUpdateCoordinator[CCM18Status]):
    """Poll a CCM18 gateway and its indoor and outdoor units."""

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
    async def _async_update_data(self) -> CCM18Status:
        try:
            status = await self.api.async_get_status()
        except CCM18Error as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"host": self.host, "error": str(err)},
            ) from err
        for index, unit in status.indoor_units.items():
            if (mode := unit.mode) is not None:
                self._last_mode[index] = mode
        return status

    @override
    async def async_shutdown(self) -> None:
        """Close the Modbus connection."""
        await super().async_shutdown()
        await self.api.close()

    def last_mode(self, index: int) -> Mode:
        """Return the last operating mode seen for a unit."""
        return self._last_mode.get(index, Mode.AUTO)

    def _control_values(self, index: int, **overrides: int) -> tuple[int, int, int]:
        """Return mode, fan and setpoint for a control write."""
        unit = self.data.indoor_units[index]
        mode_octet = overrides.get("mode_octet", unit.mode_octet)
        fan_octet = overrides.get("fan_octet", unit.fan_octet & FAN_SPEED_MASK)
        setpoint = overrides.get(
            "setpoint",
            unit.setpoint if unit.setpoint is not None else DEFAULT_SETPOINT,
        )
        return mode_octet, fan_octet, setpoint

    def _apply(self, index: int, **changes: int) -> None:
        # The gateway takes a while to report new values, so update optimistically.
        units = self.data.indoor_units
        if (unit := units.get(index)) is not None:
            units[index] = dataclasses.replace(unit, **changes)
            self.async_update_listeners()

    async def _async_set_control(
        self, index: int, mode_octet: int, fan_octet: int, setpoint: int
    ) -> None:
        try:
            await self.api.async_set_control(index, mode_octet, fan_octet, setpoint)
        except CCM18Error as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_failed"
            ) from err

    async def async_set_mode(self, index: int, mode: Mode, power_on: bool) -> None:
        """Set mode and power state of a unit."""
        mode_octet = int(mode) | (POWER_ON if power_on else 0)
        _, fan_octet, setpoint = self._control_values(index)
        await self._async_set_control(index, mode_octet, fan_octet, setpoint)
        self._last_mode[index] = mode
        self._apply(index, mode_octet=mode_octet)

    async def async_set_fan_speed(self, index: int, fan_speed: FanSpeed) -> None:
        """Set fan speed of a unit."""
        mode_octet, _, setpoint = self._control_values(index)
        fan_octet = int(fan_speed)
        await self._async_set_control(index, mode_octet, fan_octet, setpoint)
        self._apply(index, fan_octet=fan_octet)

    async def async_set_setpoint(self, index: int, temperature: int) -> None:
        """Set target temperature of a unit."""
        mode_octet, fan_octet, _ = self._control_values(index)
        await self._async_set_control(index, mode_octet, fan_octet, temperature)
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
