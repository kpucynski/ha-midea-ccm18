"""Sensors for the Midea CCM18 gateway, its indoor and outdoor units."""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfFrequency,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CCM18IndoorUnit, CCM18OutdoorUnit
from .coordinator import CCM18ConfigEntry, CCM18Coordinator
from .entity import indoor_device_info, outdoor_device_info

PARALLEL_UPDATES = 0

EEV_NOT_PRESENT = 0xFF
EEV_STEPS_PER_UNIT = 8


@dataclass(frozen=True, kw_only=True)
class CCM18OutdoorSensorDescription(SensorEntityDescription):
    """Describes an outdoor unit sensor."""

    value_fn: Callable[[CCM18OutdoorUnit], float | int | None]


@dataclass(frozen=True, kw_only=True)
class CCM18IndoorSensorDescription(SensorEntityDescription):
    """Describes an indoor unit sensor."""

    value_fn: Callable[[CCM18IndoorUnit], float | int | None]


def _temperature(
    key: str, enabled: bool = True
) -> dict[str, str | bool | SensorDeviceClass | SensorStateClass | None]:
    return {
        "key": key,
        "translation_key": key,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
        "entity_registry_enabled_default": enabled,
    }


def _eev(raw: int) -> int | None:
    return None if raw == EEV_NOT_PRESENT else raw * EEV_STEPS_PER_UNIT


OUTDOOR_SENSORS: tuple[CCM18OutdoorSensorDescription, ...] = (
    CCM18OutdoorSensorDescription(
        **_temperature("outdoor_temperature"),
        value_fn=lambda unit: unit.outdoor_temperature,
    ),
    CCM18OutdoorSensorDescription(
        **_temperature("condenser_outlet_temperature", enabled=False),
        value_fn=lambda unit: unit.condenser_outlet_temperature,
    ),
    CCM18OutdoorSensorDescription(
        **_temperature("condenser_inlet_temperature", enabled=False),
        value_fn=lambda unit: unit.condenser_inlet_temperature,
    ),
    *(
        CCM18OutdoorSensorDescription(
            **_temperature(f"discharge_temperature_{n + 1}", enabled=n == 0),
            value_fn=lambda unit, n=n: unit.discharge_temperatures[n],
        )
        for n in range(3)
    ),
    *(
        CCM18OutdoorSensorDescription(
            key=f"compressor_current_{n + 1}",
            translation_key=f"compressor_current_{n + 1}",
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            entity_registry_enabled_default=n == 0,
            value_fn=lambda unit, n=n: unit.compressor_currents[n],
        )
        for n in range(3)
    ),
    CCM18OutdoorSensorDescription(
        key="compressor_frequency",
        translation_key="compressor_frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        value_fn=lambda unit: unit.compressor_frequency,
    ),
    CCM18OutdoorSensorDescription(
        key="capacity_demand",
        translation_key="capacity_demand",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="HP",
        value_fn=lambda unit: unit.capacity_demand,
    ),
    *(
        CCM18OutdoorSensorDescription(
            key=f"eev_opening_{n + 1}",
            translation_key=f"eev_opening_{n + 1}",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement="steps",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=lambda unit, n=n: _eev(unit.eev_openings[n]),
        )
        for n in range(2)
    ),
    CCM18OutdoorSensorDescription(
        key="indoor_unit_count",
        translation_key="indoor_unit_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda unit: unit.indoor_unit_count,
    ),
)

INDOOR_SENSORS: tuple[CCM18IndoorSensorDescription, ...] = (
    CCM18IndoorSensorDescription(
        **_temperature("evaporator_temperature", enabled=False),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda unit: unit.evaporator_temperature,
    ),
    CCM18IndoorSensorDescription(
        **_temperature("evaporator_mid_temperature", enabled=False),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda unit: unit.evaporator_mid_temperature,
    ),
    CCM18IndoorSensorDescription(
        **_temperature("indoor_condenser_temperature", enabled=False),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda unit: unit.condenser_temperature,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CCM18ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for every online indoor and outdoor unit."""
    coordinator = config_entry.runtime_data
    data = coordinator.data
    async_add_entities(
        [
            *(
                CCM18OutdoorSensor(coordinator, index, description)
                for index in data.outdoor_units
                for description in OUTDOOR_SENSORS
            ),
            *(
                CCM18IndoorSensor(coordinator, index, description)
                for index in data.indoor_units
                for description in INDOOR_SENSORS
            ),
        ]
    )


class CCM18OutdoorSensor(CoordinatorEntity[CCM18Coordinator], SensorEntity):
    """A sensor of an outdoor unit."""

    _attr_has_entity_name = True
    entity_description: CCM18OutdoorSensorDescription

    def __init__(
        self,
        coordinator: CCM18Coordinator,
        index: int,
        description: CCM18OutdoorSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._index = index
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.host}.outdoor.{index}.{description.key}"
        self._attr_device_info = outdoor_device_info(coordinator, index)

    @property
    def available(self) -> bool:
        """Return True if the outdoor unit is online."""
        return super().available and self._index in self.coordinator.data.outdoor_units

    @property
    def native_value(self) -> float | int | None:
        """Return the sensor value."""
        if (unit := self.coordinator.data.outdoor_units.get(self._index)) is None:
            return None
        return self.entity_description.value_fn(unit)


class CCM18IndoorSensor(CoordinatorEntity[CCM18Coordinator], SensorEntity):
    """A sensor of an indoor unit."""

    _attr_has_entity_name = True
    entity_description: CCM18IndoorSensorDescription

    def __init__(
        self,
        coordinator: CCM18Coordinator,
        index: int,
        description: CCM18IndoorSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._index = index
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.host}.{index}.{description.key}"
        self._attr_device_info = indoor_device_info(coordinator, index)

    @property
    def available(self) -> bool:
        """Return True if the indoor unit is online."""
        return super().available and self._index in self.coordinator.data.indoor_units

    @property
    def native_value(self) -> float | int | None:
        """Return the sensor value."""
        if (unit := self.coordinator.data.indoor_units.get(self._index)) is None:
            return None
        return self.entity_description.value_fn(unit)
