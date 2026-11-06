"""Tests for CCM18 climate entities."""

from unittest.mock import AsyncMock

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_HVAC_MODE,
    ATTR_SWING_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    FAN_HIGH,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    SWING_ON,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ccm18.api import AuxFunction, CCM18Error, FanSpeed, Mode

UNIT_0 = "climate.midea_0"
UNIT_1 = "climate.midea_1"


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, mock_ccm18: AsyncMock, mock_config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the integration."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry


async def test_entities(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Test entity state for a running and a switched-off unit."""
    state = hass.states.get(UNIT_0)
    assert state.state == HVACMode.COOL
    assert state.attributes["current_temperature"] == 26.5
    assert state.attributes[ATTR_TEMPERATURE] == 24
    assert state.attributes[ATTR_FAN_MODE] == "low"
    assert state.attributes[ATTR_SWING_MODE] == "off"

    state = hass.states.get(UNIT_1)
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_FAN_MODE] == "medium"


async def test_setup_retry_when_unreachable(
    hass: HomeAssistant, mock_ccm18: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test the entry is retried when the gateway is unreachable."""
    mock_ccm18.async_get_units.side_effect = CCM18Error("timeout")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_ccm18: AsyncMock
) -> None:
    """Test unloading closes the connection."""
    await hass.config_entries.async_unload(setup_integration.entry_id)
    assert setup_integration.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(UNIT_0).state == STATE_UNAVAILABLE
    mock_ccm18.close.assert_awaited_once()


async def test_set_hvac_mode(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_ccm18: AsyncMock
) -> None:
    """Test changing mode and switching off keeps the last mode."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: UNIT_0, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    mock_ccm18.async_set_mode.assert_awaited_with(0, Mode.HEAT, True)
    assert hass.states.get(UNIT_0).state == HVACMode.HEAT

    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: UNIT_0}, blocking=True
    )
    mock_ccm18.async_set_mode.assert_awaited_with(0, Mode.HEAT, False)
    assert hass.states.get(UNIT_0).state == HVACMode.OFF

    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: UNIT_0}, blocking=True
    )
    mock_ccm18.async_set_mode.assert_awaited_with(0, Mode.HEAT, True)


async def test_turn_on_unknown_mode_uses_auto(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_ccm18: AsyncMock
) -> None:
    """Test turning on a unit whose mode has never been seen."""
    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: UNIT_1}, blocking=True
    )
    mock_ccm18.async_set_mode.assert_awaited_with(1, Mode.AUTO, True)


async def test_set_temperature(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_ccm18: AsyncMock
) -> None:
    """Test setting the target temperature together with a mode."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: UNIT_1, ATTR_TEMPERATURE: 22, ATTR_HVAC_MODE: HVACMode.COOL},
        blocking=True,
    )
    mock_ccm18.async_set_mode.assert_awaited_with(1, Mode.COOL, True)
    mock_ccm18.async_set_setpoint.assert_awaited_with(1, 22)
    assert hass.states.get(UNIT_1).attributes[ATTR_TEMPERATURE] == 22


async def test_set_fan_and_swing(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_ccm18: AsyncMock
) -> None:
    """Test fan speed and swing commands."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_FAN_MODE,
        {ATTR_ENTITY_ID: UNIT_0, ATTR_FAN_MODE: FAN_HIGH},
        blocking=True,
    )
    mock_ccm18.async_set_fan_speed.assert_awaited_with(0, FanSpeed.HIGH)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_SWING_MODE,
        {ATTR_ENTITY_ID: UNIT_0, ATTR_SWING_MODE: SWING_ON},
        blocking=True,
    )
    mock_ccm18.async_set_aux_functions.assert_awaited_with(0, AuxFunction.SWING)
    assert hass.states.get(UNIT_0).attributes[ATTR_SWING_MODE] == SWING_ON


async def test_command_failure(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_ccm18: AsyncMock
) -> None:
    """Test a failing command raises and leaves the state unchanged."""
    mock_ccm18.async_set_setpoint.side_effect = CCM18Error("timeout")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: UNIT_0, ATTR_TEMPERATURE: 20},
            blocking=True,
        )
    assert hass.states.get(UNIT_0).attributes[ATTR_TEMPERATURE] == 24
