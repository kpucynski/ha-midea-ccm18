"""Fixtures for the Midea CCM18 Modbus Gateway tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ccm18.api import (
    POWER_ON,
    SYSTEM_RUNNING,
    CCM18IndoorUnit,
    CCM18OutdoorUnit,
    CCM18Status,
    FanSpeed,
    Mode,
)
from custom_components.ccm18.const import CONF_DEVICE_ID, DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in all tests."""


def make_status() -> CCM18Status:
    """Return a cooling unit 0, a switched-off unit 1 and one outdoor unit."""
    return CCM18Status(
        system_state=SYSTEM_RUNNING,
        indoor_units={
            0: CCM18IndoorUnit(
                index=0,
                mode_octet=POWER_ON | Mode.COOL,
                fan_octet=FanSpeed.LOW,
                aux_octet=0,
                aux2_octet=0x01,
                setpoint=24,
                temperature=26.5,
                evaporator_temperature=12.0,
                evaporator_mid_temperature=12.5,
                condenser_temperature=None,
                error_code=0,
                protection_code=0,
            ),
            1: CCM18IndoorUnit(
                index=1,
                mode_octet=0,
                fan_octet=FanSpeed.MEDIUM,
                aux_octet=0,
                setpoint=21,
                temperature=24.5,
                error_code=4,
                protection_code=0,
            ),
        },
        outdoor_units={
            0: CCM18OutdoorUnit(
                index=0,
                is_running=True,
                has_error=False,
                outdoor_temperature=8.5,
                condenser_outlet_temperature=30.0,
                condenser_inlet_temperature=None,
                discharge_temperatures=(65.0, None, None),
                compressor_currents=(7, 0, 0),
                compressor_frequency=54,
                eev_openings=(60, 0xFF),
                indoor_unit_count=2,
                capacity_demand=3,
            )
        },
    )


@pytest.fixture
def mock_ccm18() -> Generator[AsyncMock]:
    """Mock the CCM18 client used by the coordinator and config flow."""
    with (
        patch(
            "custom_components.ccm18.coordinator.CCM18", autospec=True
        ) as client_class,
        patch("custom_components.ccm18.config_flow.CCM18", new=client_class),
    ):
        client = client_class.return_value
        client.async_get_status.return_value = make_status()
        client.async_get_online_units.return_value = [0, 1]
        yield client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for the gateway."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="CCM18 10.0.1.40",
        data={CONF_HOST: "10.0.1.40", CONF_PORT: 502, CONF_DEVICE_ID: 1},
    )
