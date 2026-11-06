"""The Midea CCM18 Modbus gateway integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import CCM18ConfigEntry, CCM18Coordinator

PLATFORMS: list[Platform] = [Platform.CLIMATE]


async def async_setup_entry(hass: HomeAssistant, entry: CCM18ConfigEntry) -> None:
    """Set up a CCM18 gateway from a config entry."""
    coordinator = CCM18Coordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    gateway = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, coordinator.host)},
        name=f"CCM18 {coordinator.host}",
        manufacturer="Midea",
        model="CCM18",
    )
    coordinator.gateway_device_id = gateway.id

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: CCM18ConfigEntry) -> None:
    """Unload a config entry."""
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
