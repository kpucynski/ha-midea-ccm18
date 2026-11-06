"""Climate entities for indoor units connected to a Midea CCM18 gateway."""

from typing import Any, override

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    SWING_OFF,
    SWING_ON,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_HALVES,
    PRECISION_WHOLE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import MAX_SETPOINT, MIN_SETPOINT, AuxFunction, CCM18IndoorUnit
from .const import (
    DOMAIN,
    FAN_MODE_TO_FAN_SPEED,
    FAN_SPEED_TO_FAN_MODE,
    HVAC_TO_MODE,
    MODE_TO_HVAC,
)
from .coordinator import CCM18ConfigEntry, CCM18Coordinator

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CCM18ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a climate entity for every online indoor unit."""
    coordinator = config_entry.runtime_data
    async_add_entities(CCM18Climate(coordinator, index) for index in coordinator.data)


class CCM18Climate(CoordinatorEntity[CCM18Coordinator], ClimateEntity):
    """An indoor unit connected to a CCM18 gateway."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_HALVES
    _attr_target_temperature_step = PRECISION_WHOLE
    _attr_min_temp = MIN_SETPOINT
    _attr_max_temp = MAX_SETPOINT
    _attr_hvac_modes = [HVACMode.OFF, *HVAC_TO_MODE]
    _attr_fan_modes = list(FAN_MODE_TO_FAN_SPEED)
    _attr_swing_modes = [SWING_OFF, SWING_ON]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    def __init__(self, coordinator: CCM18Coordinator, index: int) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._index = index
        self._attr_unique_id = f"{coordinator.host}.{index}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.host}.{index}")},
            name=f"Midea {index}",
            manufacturer="Midea",
            model="Indoor unit",
            via_device_id=coordinator.gateway_device_id,
        )

    @property
    def unit(self) -> CCM18IndoorUnit | None:
        """Return the current state of the indoor unit."""
        return self.coordinator.data.get(self._index)

    @property
    @override
    def available(self) -> bool:
        return super().available and self.unit is not None

    @property
    @override
    def native_current_temperature(self) -> float | None:
        return unit.temperature if (unit := self.unit) else None

    @property
    @override
    def native_target_temperature(self) -> float | None:
        return unit.setpoint if (unit := self.unit) else None

    @property
    @override
    def hvac_mode(self) -> HVACMode | None:
        if (unit := self.unit) is None:
            return None
        if not unit.is_on:
            return HVACMode.OFF
        return MODE_TO_HVAC.get(unit.mode) if unit.mode is not None else None

    @property
    @override
    def fan_mode(self) -> str | None:
        if (unit := self.unit) is None or unit.fan_speed is None:
            return None
        return FAN_SPEED_TO_FAN_MODE.get(unit.fan_speed)

    @property
    @override
    def swing_mode(self) -> str | None:
        if (unit := self.unit) is None:
            return None
        return SWING_ON if AuxFunction.SWING in unit.aux_functions else SWING_OFF

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        if (unit := self.unit) is None:
            return {}
        return {
            "error_code": unit.error_code,
            "protection_code": unit.protection_code,
            "mode_locked": unit.is_mode_locked,
        }

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self.async_set_hvac_mode(hvac_mode)
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.async_set_setpoint(self._index, round(temperature))

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_set_mode(
                self._index, self.coordinator.last_mode(self._index), power_on=False
            )
        else:
            await self.coordinator.async_set_mode(
                self._index, HVAC_TO_MODE[hvac_mode], power_on=True
            )

    @override
    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self.coordinator.async_set_fan_speed(
            self._index, FAN_MODE_TO_FAN_SPEED[fan_mode]
        )

    @override
    async def async_set_swing_mode(self, swing_mode: str) -> None:
        unit = self.unit
        assert unit is not None
        functions = unit.aux_functions & ~AuxFunction.SWING
        if swing_mode == SWING_ON:
            functions |= AuxFunction.SWING
        await self.coordinator.async_set_aux_functions(self._index, functions)

    @override
    async def async_turn_on(self) -> None:
        await self.coordinator.async_set_mode(
            self._index, self.coordinator.last_mode(self._index), power_on=True
        )

    @override
    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
