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

    Register contents are a capture from a real gateway with units 0 and 1 online.
    """
    api = CCM18("10.0.1.40")
    modbus = MagicMock(connected=True)
    input_registers = {
        0: [0, 16, 48, 25, 93, 93, 0, 54, 0, 0, 0, 0, 255, 0, 0, 0, 0, 0, 3, 0, 0, 0],
        32: [0, 16, 48, 21, 89, 90, 0, 54, 0, 0, 0, 0, 255, 0, 0, 4, 0],
    }
    coil_octets = {0: 0x88, 8: 0x80, 24: 0x04, 128: 0x00, 136: 0x02, 152: 0x00}

    async def read_input_registers(address, *, count, device_id):
        if address == 18:
            return _response(registers=input_registers[0][18:22])
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


async def test_get_units(client: tuple[CCM18, MagicMock]) -> None:
    """Test reading the state of online units."""
    api, _ = client
    units = await api.async_get_units()

    assert list(units) == [0, 1]
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
    """Test that commands target the holding registers of the right unit."""
    api, modbus = client

    await api.async_set_mode(2, Mode.HEAT, power_on=True)
    await api.async_set_mode(2, Mode.HEAT, power_on=False)
    await api.async_set_fan_speed(2, FanSpeed.HIGH)
    await api.async_set_setpoint(2, 22)
    await api.async_set_aux_functions(2, AuxFunction.SWING)

    assert [call.args for call in modbus.write_registers.await_args_list] == [
        (65, [0x84]),
        (65, [0x04]),
        (66, [0x01]),
        (67, [22]),
        (70, [0x04]),
    ]


async def test_setpoint_out_of_range(client: tuple[CCM18, MagicMock]) -> None:
    """Test that invalid setpoints are rejected before writing."""
    api, modbus = client
    with pytest.raises(ValueError):
        await api.async_set_setpoint(0, 40)
    modbus.write_registers.assert_not_awaited()


async def test_error_response(client: tuple[CCM18, MagicMock]) -> None:
    """Test that Modbus error responses raise CCM18Error."""
    api, modbus = client
    error = MagicMock()
    error.isError.return_value = True
    modbus.write_registers.return_value = error
    with pytest.raises(CCM18Error):
        await api.async_set_setpoint(0, 22)
