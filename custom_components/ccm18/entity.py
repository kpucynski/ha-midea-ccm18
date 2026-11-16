"""Shared entity helpers for the Midea CCM18 integration."""

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .coordinator import CCM18Coordinator


def gateway_device_info(coordinator: CCM18Coordinator) -> DeviceInfo:
    """Return device info for the gateway."""
    return DeviceInfo(identifiers={(DOMAIN, coordinator.host)})


def indoor_device_info(coordinator: CCM18Coordinator, index: int) -> DeviceInfo:
    """Return device info for an indoor unit."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{coordinator.host}.{index}")},
        name=f"Midea {index}",
        manufacturer="Midea",
        model="Indoor unit",
        via_device_id=coordinator.gateway_device_id,
    )


def outdoor_device_info(coordinator: CCM18Coordinator, index: int) -> DeviceInfo:
    """Return device info for an outdoor unit."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{coordinator.host}.outdoor.{index}")},
        name=f"Midea outdoor {index}",
        manufacturer="Midea",
        model="Outdoor unit",
        via_device_id=coordinator.gateway_device_id,
    )
