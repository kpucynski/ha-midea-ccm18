"""Diagnostics support for the Midea CCM18 integration."""

import dataclasses
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import CCM18ConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: CCM18ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        str(index): dataclasses.asdict(unit)
        for index, unit in config_entry.runtime_data.data.items()
    }
