"""Tests for the CCM18 sensor and binary sensor platforms."""

from unittest.mock import AsyncMock

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant.common import MockConfigEntry


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, mock_ccm18: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Set up the integration with the mocked gateway."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(
    ("entity_id", "state"),
    [
        ("sensor.midea_outdoor_0_outdoor_temperature", "8.5"),
        ("sensor.midea_outdoor_0_compressor_1_discharge_temperature", "65.0"),
        ("sensor.midea_outdoor_0_compressor_1_current", "7"),
        ("sensor.midea_outdoor_0_compressor_frequency", "54"),
        ("sensor.midea_outdoor_0_capacity_demand", "3"),
        ("sensor.midea_outdoor_0_indoor_units", "2"),
        ("binary_sensor.ccm18_10_0_1_40_running", STATE_ON),
        ("binary_sensor.ccm18_10_0_1_40_problem", STATE_OFF),
        ("binary_sensor.midea_outdoor_0_running", STATE_ON),
        ("binary_sensor.midea_outdoor_0_problem", STATE_OFF),
        ("binary_sensor.midea_0_problem", STATE_OFF),
        ("binary_sensor.midea_1_problem", STATE_ON),
    ],
)
async def test_states(hass: HomeAssistant, entity_id: str, state: str) -> None:
    """Test sensor states for the gateway, outdoor and indoor units."""
    assert (entity := hass.states.get(entity_id))
    assert entity.state == state


@pytest.mark.usefixtures("setup_integration")
async def test_indoor_problem_attributes(hass: HomeAssistant) -> None:
    """Test that the raw error codes are exposed."""
    entity = hass.states.get("binary_sensor.midea_1_problem")
    assert entity.attributes["error_code"] == 4
    assert entity.attributes["protection_code"] == 0


@pytest.mark.usefixtures("setup_integration")
async def test_disabled_by_default(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test that secondary sensors are registered but disabled."""
    for entity_id in (
        "sensor.midea_outdoor_0_condenser_inlet_temperature",
        "sensor.midea_outdoor_0_expansion_valve_1_opening",
        "sensor.midea_0_evaporator_pipe_temperature",
    ):
        assert (entry := entity_registry.async_get(entity_id))
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entity_id) is None


async def test_disabled_sensor_values(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_ccm18: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test values of sensors that are disabled by default once enabled."""
    expected = {
        "sensor.midea_outdoor_0_condenser_inlet_temperature": STATE_UNKNOWN,
        "sensor.midea_outdoor_0_expansion_valve_1_opening": "480",
        "sensor.midea_outdoor_0_expansion_valve_2_opening": STATE_UNKNOWN,
        "sensor.midea_0_evaporator_pipe_temperature": "12.0",
    }
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    for entity_id in expected:
        entity_registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    for entity_id, state in expected.items():
        assert hass.states.get(entity_id).state == state
