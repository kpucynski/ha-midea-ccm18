"""Async Modbus TCP client for the Midea CCM18 BMS gateway."""

import asyncio
from dataclasses import dataclass
from enum import IntFlag
import logging

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

_LOGGER = logging.getLogger(__name__)

MAX_INDOOR_UNITS = 64
REGISTERS_PER_UNIT = 32
COILS_PER_UNIT = 128

# Input register offsets inside an indoor unit block (address = unit * 32 + offset).
IR_SETPOINT = 3
IR_INDOOR_TEMP = 4
IR_ERROR = 15
IR_PROTECTION = 16
IR_BLOCK_SIZE = 17
# Gateway-wide input registers, located in the block of indoor unit 0.
IR_INDOOR_ONLINE = 18
IR_INDOOR_ONLINE_COUNT = 4

# Coil octets inside an indoor unit block (address = unit * 128 + octet * 8).
COIL_OCTET_MODE = 0
COIL_OCTET_FAN = 1
COIL_OCTET_AUX = 3

# Holding register offsets inside an indoor unit block (address = unit * 32 + offset).
# Offset 0 of unit 0 switches the whole refrigerant system and must never be written.
HR_MODE = 1
HR_FAN = 2
HR_SETPOINT = 3
HR_AUX = 6

MIN_SETPOINT = 16
MAX_SETPOINT = 32


class Mode(IntFlag):
    """Operating mode bits, shared by mode coils and the mode holding register."""

    FAN = 0x01
    DRY = 0x02
    HEAT = 0x04
    COOL = 0x08
    AUTO = 0x10


MODE_MASK = 0x1F
MODE_LOCKED = 0x20
POWER_ON = 0x80


class FanSpeed(IntFlag):
    """Fan speed bits, shared by fan coils and the fan holding register."""

    HIGH = 0x01
    MEDIUM = 0x02
    LOW = 0x04
    AUTO = 0x80


class AuxFunction(IntFlag):
    """Auxiliary function bits, shared by coils and the auxiliary holding register."""

    ECO = 0x01
    ELECTRIC_HEATER = 0x02
    SWING = 0x04


class CCM18Error(Exception):
    """Raised when the gateway cannot be reached or rejects a request."""


def decode_temperature(raw: int) -> float | None:
    """Decode a pipe/room temperature register (0..240 maps to -20..100 °C)."""
    if raw > 240:
        return None
    return raw / 2 - 20


@dataclass
class CCM18IndoorUnit:
    """State of a single indoor unit."""

    index: int
    mode_octet: int
    fan_octet: int
    aux_octet: int
    setpoint: int | None
    temperature: float | None
    error_code: int
    protection_code: int

    @property
    def is_on(self) -> bool:
        """Return True if the unit is running."""
        return bool(self.mode_octet & POWER_ON)

    @property
    def mode(self) -> Mode | None:
        """Return the active operating mode, if exactly one is reported."""
        mode = Mode(self.mode_octet & MODE_MASK)
        return mode if mode.bit_count() == 1 else None

    @property
    def is_mode_locked(self) -> bool:
        """Return True if the mode is locked by a central controller."""
        return bool(self.mode_octet & MODE_LOCKED)

    @property
    def fan_speed(self) -> FanSpeed | None:
        """Return the active fan speed, if exactly one is reported."""
        fan = FanSpeed(
            self.fan_octet
            & (FanSpeed.HIGH | FanSpeed.MEDIUM | FanSpeed.LOW | FanSpeed.AUTO)
        )
        return fan if fan.bit_count() == 1 else None

    @property
    def aux_functions(self) -> AuxFunction:
        """Return active auxiliary functions."""
        return AuxFunction(
            self.aux_octet
            & (AuxFunction.ECO | AuxFunction.ELECTRIC_HEATER | AuxFunction.SWING)
        )


class CCM18:
    """Client for a CCM18 gateway reachable over Modbus TCP."""

    def __init__(
        self, host: str, port: int = 502, device_id: int = 1, timeout: float = 5
    ) -> None:
        """Initialize the client."""
        self.host = host
        self._device_id = device_id
        self._client = AsyncModbusTcpClient(host, port=port, timeout=timeout, retries=1)
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        """Close the connection."""
        self._client.close()

    async def _ensure_connected(self) -> None:
        if not self._client.connected and not await self._client.connect():
            raise CCM18Error(f"Unable to connect to {self.host}")

    async def _read_input_registers(self, address: int, count: int) -> list[int]:
        try:
            response = await self._client.read_input_registers(
                address, count=count, device_id=self._device_id
            )
        except ModbusException as err:
            raise CCM18Error(f"Reading input registers at {address} failed") from err
        if response.isError():
            raise CCM18Error(f"Reading input registers at {address} failed: {response}")
        return response.registers

    async def _read_coil_octet(self, address: int) -> int:
        # The gateway returns corrupted data when more than 8 coils are read at once.
        try:
            response = await self._client.read_coils(
                address, count=8, device_id=self._device_id
            )
        except ModbusException as err:
            raise CCM18Error(f"Reading coils at {address} failed") from err
        if response.isError():
            raise CCM18Error(f"Reading coils at {address} failed: {response}")
        return sum(1 << bit for bit, value in enumerate(response.bits[:8]) if value)

    async def _write_register(self, address: int, value: int) -> None:
        # The gateway only supports function code 0x10 (write multiple registers).
        async with self._lock:
            await self._ensure_connected()
            try:
                response = await self._client.write_registers(
                    address, [value], device_id=self._device_id
                )
            except ModbusException as err:
                raise CCM18Error(f"Writing register {address} failed") from err
            if response.isError():
                raise CCM18Error(f"Writing register {address} failed: {response}")

    async def _get_online_unit_indexes(self) -> list[int]:
        bitmaps = await self._read_input_registers(
            IR_INDOOR_ONLINE, IR_INDOOR_ONLINE_COUNT
        )
        return [
            word * 16 + bit
            for word, bitmap in enumerate(bitmaps)
            for bit in range(16)
            if bitmap >> bit & 1
        ]

    async def _get_unit(self, index: int) -> CCM18IndoorUnit:
        registers = await self._read_input_registers(
            index * REGISTERS_PER_UNIT, IR_BLOCK_SIZE
        )
        coil_base = index * COILS_PER_UNIT
        setpoint = registers[IR_SETPOINT]
        return CCM18IndoorUnit(
            index=index,
            mode_octet=await self._read_coil_octet(coil_base + COIL_OCTET_MODE * 8),
            fan_octet=await self._read_coil_octet(coil_base + COIL_OCTET_FAN * 8),
            aux_octet=await self._read_coil_octet(coil_base + COIL_OCTET_AUX * 8),
            setpoint=setpoint if MIN_SETPOINT <= setpoint <= MAX_SETPOINT else None,
            temperature=decode_temperature(registers[IR_INDOOR_TEMP]),
            error_code=registers[IR_ERROR],
            protection_code=registers[IR_PROTECTION],
        )

    async def async_get_online_units(self) -> list[int]:
        """Return the indexes of indoor units reported online by the gateway."""
        async with self._lock:
            await self._ensure_connected()
            return await self._get_online_unit_indexes()

    async def async_get_units(self) -> dict[int, CCM18IndoorUnit]:
        """Return the state of every online indoor unit."""
        async with self._lock:
            await self._ensure_connected()
            return {
                index: await self._get_unit(index)
                for index in await self._get_online_unit_indexes()
            }

    async def async_set_mode(self, index: int, mode: Mode, power_on: bool) -> None:
        """Set the operating mode and power state of an indoor unit."""
        value = int(mode) | (POWER_ON if power_on else 0)
        _LOGGER.debug("Unit %s: mode register <- %#04x", index, value)
        await self._write_register(index * REGISTERS_PER_UNIT + HR_MODE, value)

    async def async_set_fan_speed(self, index: int, fan_speed: FanSpeed) -> None:
        """Set the fan speed of an indoor unit."""
        _LOGGER.debug("Unit %s: fan register <- %#04x", index, int(fan_speed))
        await self._write_register(index * REGISTERS_PER_UNIT + HR_FAN, int(fan_speed))

    async def async_set_setpoint(self, index: int, temperature: int) -> None:
        """Set the target temperature of an indoor unit."""
        if not MIN_SETPOINT <= temperature <= MAX_SETPOINT:
            raise ValueError(
                f"Setpoint {temperature} outside {MIN_SETPOINT}-{MAX_SETPOINT}"
            )
        _LOGGER.debug("Unit %s: setpoint register <- %s", index, temperature)
        await self._write_register(
            index * REGISTERS_PER_UNIT + HR_SETPOINT, temperature
        )

    async def async_set_aux_functions(self, index: int, functions: AuxFunction) -> None:
        """Set the auxiliary functions (eco, electric heater, swing) of an indoor unit."""
        _LOGGER.debug("Unit %s: aux register <- %#04x", index, int(functions))
        await self._write_register(index * REGISTERS_PER_UNIT + HR_AUX, int(functions))
