"""Binary sensors for the Midea CCM18 gateway, its indoor and outdoor units."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import CCM18ConfigEntry, CCM18Coordinator
from .entity import gateway_device_info, indoor_device_info, outdoor_device_info

PARALLEL_UPDATES = 0

RUNNING = BinarySensorEntityDescription(
    key="running", device_class=BinarySensorDeviceClass.RUNNING
)
PROBLEM = BinarySensorEntityDescription(
    key="problem", device_class=BinarySensorDeviceClass.PROBLEM
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CCM18ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors for the gateway and every online unit."""
    coordinator = config_entry.runtime_data
    data = coordinator.data
    async_add_entities(
        [
            CCM18GatewayBinarySensor(coordinator, RUNNING),
            CCM18GatewayBinarySensor(coordinator, PROBLEM),
            *(
                CCM18OutdoorBinarySensor(coordinator, index, description)
                for index in data.outdoor_units
                for description in (RUNNING, PROBLEM)
            ),
            *(
                CCM18IndoorProblemSensor(coordinator, index)
                for index in data.indoor_units
            ),
        ]
    )


class CCM18GatewayBinarySensor(CoordinatorEntity[CCM18Coordinator], BinarySensorEntity):
    """Running or problem state of the whole refrigerant system."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: CCM18Coordinator,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.host}.system.{description.key}"
        self._attr_device_info = gateway_device_info(coordinator)

    @property
    def is_on(self) -> bool:
        """Return the system state."""
        status = self.coordinator.data
        if self.entity_description.key == RUNNING.key:
            return status.is_running
        return status.has_error


class CCM18OutdoorBinarySensor(CoordinatorEntity[CCM18Coordinator], BinarySensorEntity):
    """Running or problem state of an outdoor unit."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CCM18Coordinator,
        index: int,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
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
    def is_on(self) -> bool | None:
        """Return the outdoor unit state."""
        if (unit := self.coordinator.data.outdoor_units.get(self._index)) is None:
            return None
        if self.entity_description.key == RUNNING.key:
            return unit.is_running
        return unit.has_error


class CCM18IndoorProblemSensor(CoordinatorEntity[CCM18Coordinator], BinarySensorEntity):
    """Error or protection state of an indoor unit."""

    _attr_has_entity_name = True
    entity_description = PROBLEM

    def __init__(self, coordinator: CCM18Coordinator, index: int) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._index = index
        self._attr_unique_id = f"{coordinator.host}.{index}.problem"
        self._attr_device_info = indoor_device_info(coordinator, index)

    @property
    def available(self) -> bool:
        """Return True if the indoor unit is online."""
        return super().available and self._index in self.coordinator.data.indoor_units

    @property
    def is_on(self) -> bool | None:
        """Return True if the unit reports an error or protection."""
        if (unit := self.coordinator.data.indoor_units.get(self._index)) is None:
            return None
        return bool(unit.error_code or unit.protection_code)

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        """Return the raw error and protection codes."""
        if (unit := self.coordinator.data.indoor_units.get(self._index)) is None:
            return {}
        return {
            "error_code": unit.error_code,
            "protection_code": unit.protection_code,
        }
