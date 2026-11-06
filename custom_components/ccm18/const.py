"""Constants for the Midea CCM18 integration."""

from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    HVACMode,
)

from .api import FanSpeed, Mode

DOMAIN = "ccm18"

CONF_DEVICE_ID = "device_id"

DEFAULT_PORT = 502
DEFAULT_DEVICE_ID = 1
DEFAULT_INTERVAL = 30
DEFAULT_TIMEOUT = 5

MODE_TO_HVAC: dict[Mode, HVACMode] = {
    Mode.FAN: HVACMode.FAN_ONLY,
    Mode.DRY: HVACMode.DRY,
    Mode.HEAT: HVACMode.HEAT,
    Mode.COOL: HVACMode.COOL,
    Mode.AUTO: HVACMode.AUTO,
}
HVAC_TO_MODE: dict[HVACMode, Mode] = {hvac: mode for mode, hvac in MODE_TO_HVAC.items()}

FAN_SPEED_TO_FAN_MODE: dict[FanSpeed, str] = {
    FanSpeed.AUTO: FAN_AUTO,
    FanSpeed.LOW: FAN_LOW,
    FanSpeed.MEDIUM: FAN_MEDIUM,
    FanSpeed.HIGH: FAN_HIGH,
}
FAN_MODE_TO_FAN_SPEED: dict[str, FanSpeed] = {
    fan_mode: speed for speed, fan_mode in FAN_SPEED_TO_FAN_MODE.items()
}
