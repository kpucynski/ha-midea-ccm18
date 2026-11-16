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

MAX_OUTDOOR_UNITS = 4

# Input register offsets inside an indoor unit block (address = unit * 32 + offset).
IR_SETPOINT = 3
IR_INDOOR_TEMP = 4
IR_EVAPORATOR_TEMP = 5
IR_EVAPORATOR_MID_TEMP = 6
IR_CONDENSER_TEMP = 7
IR_ERROR = 15
IR_PROTECTION = 16
IR_BLOCK_SIZE = 17

# Gateway-wide input registers, located in the block of indoor unit 0.
IR_SYSTEM_STATE = 0
IR_OUTDOOR_ONLINE = 17
IR_INDOOR_ONLINE = 18
IR_OUTDOOR_ERROR = 22
IR_OUTDOOR_RUNNING = 23
IR_GATEWAY_BLOCK_SIZE = 32

SYSTEM_RUNNING = 0x01
SYSTEM_ERROR = 0x02
SYSTEM_REMOTE = 0x04

# Outdoor unit input registers (address = 2048 + unit * 32 + offset).
IR_OUTDOOR_BASE = 2048
IR_OUTDOOR_TEMP = 3
IR_OUTDOOR_CONDENSER_OUTLET_TEMP = 4
IR_OUTDOOR_CONDENSER_INLET_TEMP = 5
IR_OUTDOOR_DISCHARGE_TEMPS = (6, 7, 8)
IR_OUTDOOR_INDOOR_COUNT = 9
IR_OUTDOOR_COMPRESSOR_CURRENTS = (10, 11, 12)
IR_OUTDOOR_FREQUENCY = 13
IR_OUTDOOR_EEV_OPENINGS = (14, 15)
IR_OUTDOOR_CAPACITY = 16
IR_OUTDOOR_BLOCK_SIZE = 17

# Coil octets inside an indoor unit block (address = unit * 128 + octet * 8).
COIL_OCTET_MODE = 0
COIL_OCTET_FAN = 1
COIL_OCTET_AUX = 3
COIL_OCTET_AUX2 = 4
COIL_HORIZONTAL_SWING = 0x01

# Holding register offsets inside an indoor unit block (address = unit * 32 + offset).
# Offset 0 of unit 0 switches the whole refrigerant system and must never be written.
HR_MODE = 1
HR_AUX = 6

MIN_SETPOINT = 16
MAX_SETPOINT = 32
DEFAULT_SETPOINT = 25


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


FAN_SPEED_MASK = int(FanSpeed.HIGH | FanSpeed.MEDIUM | FanSpeed.LOW | FanSpeed.AUTO)


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
    aux2_octet: int = 0
    evaporator_temperature: float | None = None
    evaporator_mid_temperature: float | None = None
    condenser_temperature: float | None = None

    @property
    def horizontal_swing(self) -> bool:
        """Return True if horizontal swing is active."""
        return bool(self.aux2_octet & COIL_HORIZONTAL_SWING)

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


@dataclass
class CCM18OutdoorUnit:
    """State of a single outdoor unit."""

    index: int
    is_running: bool
    has_error: bool
    outdoor_temperature: float | None
    condenser_outlet_temperature: float | None
    condenser_inlet_temperature: float | None
    discharge_temperatures: tuple[float | None, ...]
    compressor_currents: tuple[int, ...]
    compressor_frequency: int
    eev_openings: tuple[int, ...]
    indoor_unit_count: int
    capacity_demand: int


@dataclass
class CCM18Status:
    """State of the gateway and every online indoor and outdoor unit."""

    system_state: int
    indoor_units: dict[int, CCM18IndoorUnit]
    outdoor_units: dict[int, CCM18OutdoorUnit]

    @property
    def is_running(self) -> bool:
        """Return True if the refrigerant system is running."""
        return bool(self.system_state & SYSTEM_RUNNING)

    @property
    def has_error(self) -> bool:
        """Return True if the refrigerant system reports an error."""
        return bool(self.system_state & SYSTEM_ERROR)

    @property
    def is_remote(self) -> bool:
        """Return True if the system is in remote (not local) control."""
        return bool(self.system_state & SYSTEM_REMOTE)


def _bits(bitmaps: list[int]) -> list[int]:
    return [
        word * 16 + bit
        for word, bitmap in enumerate(bitmaps)
        for bit in range(16)
        if bitmap >> bit & 1
    ]


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

    async def _write_registers(self, address: int, values: list[int]) -> None:
        # The gateway only supports function code 0x10 (write multiple registers).
        async with self._lock:
            await self._ensure_connected()
            try:
                response = await self._client.write_registers(
                    address, values, device_id=self._device_id
                )
            except ModbusException as err:
                raise CCM18Error(f"Writing registers at {address} failed") from err
            if response.isError():
                raise CCM18Error(f"Writing registers at {address} failed: {response}")

    async def _read_gateway_block(self) -> list[int]:
        return await self._read_input_registers(0, IR_GATEWAY_BLOCK_SIZE)

    async def _get_indoor_unit(
        self, index: int, registers: list[int]
    ) -> CCM18IndoorUnit:
        coil_base = index * COILS_PER_UNIT
        setpoint = registers[IR_SETPOINT]
        return CCM18IndoorUnit(
            index=index,
            mode_octet=await self._read_coil_octet(coil_base + COIL_OCTET_MODE * 8),
            fan_octet=await self._read_coil_octet(coil_base + COIL_OCTET_FAN * 8),
            aux_octet=await self._read_coil_octet(coil_base + COIL_OCTET_AUX * 8),
            aux2_octet=await self._read_coil_octet(coil_base + COIL_OCTET_AUX2 * 8),
            setpoint=setpoint if MIN_SETPOINT <= setpoint <= MAX_SETPOINT else None,
            temperature=decode_temperature(registers[IR_INDOOR_TEMP]),
            evaporator_temperature=decode_temperature(registers[IR_EVAPORATOR_TEMP]),
            evaporator_mid_temperature=decode_temperature(
                registers[IR_EVAPORATOR_MID_TEMP]
            ),
            condenser_temperature=decode_temperature(registers[IR_CONDENSER_TEMP]),
            error_code=registers[IR_ERROR],
            protection_code=registers[IR_PROTECTION],
        )

    async def _get_outdoor_unit(
        self, index: int, running: int, error: int
    ) -> CCM18OutdoorUnit:
        registers = await self._read_input_registers(
            IR_OUTDOOR_BASE + index * REGISTERS_PER_UNIT, IR_OUTDOOR_BLOCK_SIZE
        )
        return CCM18OutdoorUnit(
            index=index,
            is_running=bool(running >> index & 1),
            has_error=bool(error >> index & 1),
            outdoor_temperature=decode_temperature(registers[IR_OUTDOOR_TEMP]),
            condenser_outlet_temperature=decode_temperature(
                registers[IR_OUTDOOR_CONDENSER_OUTLET_TEMP]
            ),
            condenser_inlet_temperature=decode_temperature(
                registers[IR_OUTDOOR_CONDENSER_INLET_TEMP]
            ),
            discharge_temperatures=tuple(
                decode_temperature(registers[offset])
                for offset in IR_OUTDOOR_DISCHARGE_TEMPS
            ),
            compressor_currents=tuple(
                registers[offset] for offset in IR_OUTDOOR_COMPRESSOR_CURRENTS
            ),
            compressor_frequency=registers[IR_OUTDOOR_FREQUENCY],
            eev_openings=tuple(registers[offset] for offset in IR_OUTDOOR_EEV_OPENINGS),
            indoor_unit_count=registers[IR_OUTDOOR_INDOOR_COUNT],
            capacity_demand=registers[IR_OUTDOOR_CAPACITY],
        )

    async def async_get_online_units(self) -> list[int]:
        """Return the indexes of indoor units reported online by the gateway."""
        async with self._lock:
            await self._ensure_connected()
            gateway = await self._read_gateway_block()
        return _bits(gateway[IR_INDOOR_ONLINE : IR_INDOOR_ONLINE + 4])

    async def async_get_status(self) -> CCM18Status:
        """Return the state of the gateway and every online unit."""
        async with self._lock:
            await self._ensure_connected()
            gateway = await self._read_gateway_block()
            indoor_units = {}
            for index in _bits(gateway[IR_INDOOR_ONLINE : IR_INDOOR_ONLINE + 4]):
                registers = (
                    gateway
                    if index == 0
                    else await self._read_input_registers(
                        index * REGISTERS_PER_UNIT, IR_BLOCK_SIZE
                    )
                )
                indoor_units[index] = await self._get_indoor_unit(index, registers)
            outdoor_units = {
                index: await self._get_outdoor_unit(
                    index, gateway[IR_OUTDOOR_RUNNING], gateway[IR_OUTDOOR_ERROR]
                )
                for index in _bits([gateway[IR_OUTDOOR_ONLINE]])
                if index < MAX_OUTDOOR_UNITS
            }
        return CCM18Status(
            system_state=gateway[IR_SYSTEM_STATE],
            indoor_units=indoor_units,
            outdoor_units=outdoor_units,
        )

    async def async_set_control(
        self, index: int, mode_octet: int, fan_octet: int, setpoint: int
    ) -> None:
        """Set mode, fan and setpoint of an indoor unit.

        The gateway web UI always writes these three holding registers together.
        Writing the fan register alone with auto (0x80) can clear the power bit,
        so callers must pass the current mode and setpoint alongside any change.
        """
        if not MIN_SETPOINT <= setpoint <= MAX_SETPOINT:
            raise ValueError(
                f"Setpoint {setpoint} outside {MIN_SETPOINT}-{MAX_SETPOINT}"
            )
        _LOGGER.debug(
            "Unit %s: control <- mode=%#04x fan=%#04x setpoint=%s",
            index,
            mode_octet,
            fan_octet,
            setpoint,
        )
        await self._write_registers(
            index * REGISTERS_PER_UNIT + HR_MODE,
            [mode_octet, fan_octet, setpoint],
        )

    async def async_set_aux_functions(self, index: int, functions: AuxFunction) -> None:
        """Set the auxiliary functions (eco, electric heater, swing) of an indoor unit."""
        _LOGGER.debug("Unit %s: aux register <- %#04x", index, int(functions))
        await self._write_registers(
            index * REGISTERS_PER_UNIT + HR_AUX, [int(functions)]
        )
