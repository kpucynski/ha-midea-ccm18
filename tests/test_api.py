"""Tests for the CCM18 Modbus client."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ccm18.api import (
    CCM18,
    AuxFunction,
    CCM18Error,
    FanSpeed,
    Mode,
    decode_temperature,
)


def _response(**kwargs) -> MagicMock:
    response = MagicMock(**kwargs)
    response.isError.return_value = False
    return response


@pytest.fixture
async def client() -> tuple[CCM18, MagicMock]:
    """Return a CCM18 client backed by a fake Modbus connection.

    Indoor unit registers are a capture from a real gateway with units 0 and 1
    online; the system state and outdoor unit 0 are synthetic.
    """
    api = CCM18("10.0.1.40")
    modbus = MagicMock(connected=True)
    gateway = [0] * 32
    gateway[:22] = [5, 16, 48, 25, 93, 93, 0, 54, 0, 0, 0, 0, 255, 0, 0, 0, 0, 1, 3]
    gateway[23] = 0x01
    input_registers = {
        0: gateway,
        32: [0, 16, 48, 21, 89, 90, 0, 54, 0, 0, 0, 0, 255, 0, 0, 4, 0],
        2048: [0, 0, 0, 57, 100, 255, 170, 255, 255, 2, 7, 0, 0, 54, 8, 255, 3],
    }
    coil_octets = {
        0: 0x88,
        8: 0x80,
        24: 0x04,
        32: 0x01,
        128: 0x00,
        136: 0x02,
        152: 0x00,
        160: 0x00,
    }

    async def read_input_registers(address, *, count, device_id):
        return _response(registers=input_registers[address][:count])

    async def read_coils(address, *, count, device_id):
        assert count == 8
        octet = coil_octets[address]
        return _response(bits=[bool(octet >> bit & 1) for bit in range(8)])

    modbus.read_input_registers = read_input_registers
    modbus.read_coils = read_coils
    modbus.write_registers = AsyncMock(return_value=_response())
    api._client = modbus
    return api, modbus


def test_decode_temperature() -> None:
    """Test temperature decoding."""
    assert decode_temperature(0) == -20
    assert decode_temperature(93) == 26.5
    assert decode_temperature(240) == 100
    assert decode_temperature(255) is None


async def test_get_online_units(client: tuple[CCM18, MagicMock]) -> None:
    """Test reading the online indoor unit bitmap."""
    api, _ = client
    assert await api.async_get_online_units() == [0, 1]


async def test_get_status(client: tuple[CCM18, MagicMock]) -> None:
    """Test reading the state of the gateway and online units."""
    api, _ = client
    status = await api.async_get_status()

    assert status.is_running
    assert not status.has_error
    assert status.is_remote

    assert list(status.outdoor_units) == [0]
    outdoor = status.outdoor_units[0]
    assert outdoor.is_running
    assert not outdoor.has_error
    assert outdoor.outdoor_temperature == 8.5
    assert outdoor.condenser_outlet_temperature == 30
    assert outdoor.condenser_inlet_temperature is None
    assert outdoor.discharge_temperatures == (65, None, None)
    assert outdoor.indoor_unit_count == 2
    assert outdoor.compressor_currents == (7, 0, 0)
    assert outdoor.compressor_frequency == 54
    assert outdoor.eev_openings == (8, 255)
    assert outdoor.capacity_demand == 3

    units = status.indoor_units
    assert list(units) == [0, 1]
    assert units[0].horizontal_swing
    assert not units[1].horizontal_swing
    assert units[0].evaporator_temperature == 26.5
    assert units[0].evaporator_mid_temperature == -20
    assert units[0].condenser_temperature == 7
    assert units[0].is_on
    assert units[0].mode is Mode.COOL
    assert units[0].fan_speed is FanSpeed.AUTO
    assert units[0].aux_functions == AuxFunction.SWING
    assert units[0].setpoint == 25
    assert units[0].temperature == 26.5
    assert not units[1].is_on
    assert units[1].mode is None
    assert units[1].fan_speed is FanSpeed.MEDIUM
    assert units[1].temperature == 24.5
    assert units[1].error_code == 4


async def test_writes_use_unit_offsets(client: tuple[CCM18, MagicMock]) -> None:
    """Test that control writes target mode/fan/setpoint as one block."""
    api, modbus = client

    await api.async_set_control(2, 0x84, FanSpeed.AUTO, 22)
    await api.async_set_control(2, 0x04, FanSpeed.HIGH, 22)
    await api.async_set_aux_functions(2, AuxFunction.SWING)

    assert [call.args for call in modbus.write_registers.await_args_list] == [
        (65, [0x84, 0x80, 22]),
        (65, [0x04, 0x01, 22]),
        (70, [0x04]),
    ]


async def test_setpoint_out_of_range(client: tuple[CCM18, MagicMock]) -> None:
    """Test that invalid setpoints are rejected before writing."""
    api, modbus = client
    with pytest.raises(ValueError):
        await api.async_set_control(0, 0x88, FanSpeed.LOW, 40)
    modbus.write_registers.assert_not_awaited()


async def test_error_response(client: tuple[CCM18, MagicMock]) -> None:
    """Test that Modbus error responses raise CCM18Error."""
    api, modbus = client
    error = MagicMock()
    error.isError.return_value = True
    modbus.write_registers.return_value = error
    with pytest.raises(CCM18Error):
        await api.async_set_control(0, 0x88, FanSpeed.LOW, 22)
