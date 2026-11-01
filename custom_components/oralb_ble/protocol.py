"""Pure protocol parsing/encoding for Oral-B BLE toothbrushes.

All knowledge in this module comes from the shipped Android app
``com.pg.oralb.oralbapp`` 10.8.1 (classes ``codes.alchemy.oralb.blesdk``) and
was cross-checked against the advertisement bytes described in
``Bluetooth-Devices/oralb-ble``.

The BLE advertisement payload handed to us by Home Assistant/bleak starts at
the *protocol version* byte.  The raw over-the-air AD structure is::

    06 FF DC 00 | 09 31 32 03 00 00 00 01 00 00
    len type cid  |  protocol, type, sw, state, status, min, sec, mode,
                     progress, quadrant/sector-timer, total-quadrants

The app's own ``PGPeripheral`` keeps the ``len/type/cid`` prefix, which is why
its byte indices are four higher than the indices used here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .const import (
    ACCESS_CONTROL_KEY,
    CONFIGURE_BRUSH_MODES,
    CONFIGURE_BRUSH_TIMER,
    CONFIGURE_DASHBOARD,
    CONFIGURE_EXTEND_CONNECTION,
    CONFIGURE_MY_COLOR,
    CONFIGURE_NOTIFICATION_CLEAR,
    CONFIGURE_PRESSURE,
    CONFIGURE_QUADRANT_TIMERS,
    CONFIGURE_READ_DATA,
    CONFIGURE_READ_METADATA,
    CONFIGURE_READ_PARAM,
    CONFIGURE_REFILL_REMINDER,
    CONFIGURE_RESET_SETTINGS,
    CONFIGURE_RTC,
    CONFIGURE_SMART_GUIDE,
    CONFIGURE_START_WEEK_DAY,
    CONFIGURE_TONGUE_TIME,
    CONTROL_DISABLE_ALL_MOTOR_RAMPING,
    CONTROL_ENABLE_ALL_MOTOR_RAMPING,
    CONTROL_ENABLE_LOW_CHARGE_ONLY_MOTOR_RAMPING,
    CONTROL_ENABLE_SOFT_START_ONLY_MOTOR_RAMPING,
    CONTROL_PRESSURE_CONFIGURATION,
    CONTROL_SET_MODE,
    CONTROL_TONGUE_TIME,
    PROTOCOL_V001,
    PROTOCOL_V003,
    PROTOCOL_V006,
    PROTOCOL_V007,
    PROTOCOL_V008,
    PROTOCOL_V009,
    RTC_EPOCH_MS,
)

# ---------------------------------------------------------------------------
# Device types (manufacturer data byte 1 / Brush.Type in the app)
# ---------------------------------------------------------------------------

DEVICE_TYPES: dict[int, str] = {
    0: "D36 (X Mode)",
    1: "D36 (6 Mode)",
    2: "D36 (5 Mode)",
    3: "D36 (Experimental)",
    32: "D701 (X Mode)",
    33: "D701 (6 Mode)",
    34: "D701 (5 Mode)",
    39: "D700 (5 Mode)",
    40: "D700 (4 Mode)",
    41: "D700 (6 Mode)",
    43: "Oral-B iO Series 6",
    48: "Oral-B iO (X Mode)",
    49: "Oral-B iO",
    50: "Oral-B iO (Big TI)",
    52: "Oral-B iO4",
    53: "Oral-B iO5",
    54: "Oral-B iO (E-Platform)",
    63: "D36 (Experimental)",
    64: "D21 (X Mode)",
    65: "D21 (4 Mode)",
    66: "D21 (3 Mode)",
    67: "D21 (2A Mode)",
    68: "D21 (2B Mode)",
    69: "D21 (3 Mode Whitening)",
    70: "D21 (1 Mode)",
    80: "D601 (X Mode)",
    81: "D601 (5 Mode)",
    82: "D601 (4 Mode)",
    83: "D601 (3A Mode)",
    84: "D601 (2A Mode)",
    85: "D601 (2B Mode)",
    86: "D601 (3B Mode)",
    87: "D601 (1 Mode)",
    112: "D706 (X Mode)",
    113: "D706 (6 Mode)",
    114: "D706 (5 Mode)",
    117: "D706 (X Mode, China)",
    118: "D706 (6 Mode, China)",
    119: "D706 (5 Mode, China)",
    153: "Unknown",
    165: "HCB G5",
    166: "HCB E-Platform",
    255: "Experimental",
}

# Sonos sub-model (manufacturer data byte 10 / SonosMetadata.Model).
SONOS_MODELS: dict[int, str] = {
    0: "Undefined",
    1: "M9",
    2: "M8",
    3: "M7",
    4: "M6",
    5: "M5",
    6: "M4",
    16: "M10",
}

# DeviceState.State (GATT FF04 byte 0 / advertisement byte 3).
STATES: dict[int, str] = {
    0: "unknown",
    1: "init",
    2: "idle",
    3: "running",
    4: "charging",
    5: "setup",
    6: "flight menu",
    7: "charging forbidden",
    8: "pre-run",
    9: "paused",
    10: "post-brushing statistics",
    113: "final test",
    114: "pcb test",
    115: "sleeping",
    116: "transport",
    117: "calibration test",
}

# BrushingMode.Mode, protocol < V006.
MODES_LEGACY: dict[int, str] = {
    0: "off",
    1: "daily clean",
    2: "sensitive",
    3: "massage",
    4: "whitening",
    5: "deep clean",
    6: "tongue clean",
    7: "pro clean",
}

# BrushingMode.Mode, protocol >= V006.
MODES_V006: dict[int, str] = {
    0: "daily clean",
    1: "sensitive",
    2: "gum care",
    3: "whiten",
    4: "intense",
    5: "super sensitive",
    6: "tongue cleaning",
    7: "off",
    8: "settings",
    11: "smart adapt",
    12: "gentle white",
}

# Pressure.State (GATT FF0B byte 0 for protocol >= V007).
PRESSURE_STATES: dict[int, str] = {0: "low", 1: "normal", 2: "high"}

QUADRANTS: dict[int, str] = {
    0: "none",
    1: "1st",
    2: "2nd",
    3: "3rd",
    4: "4th",
    5: "5th",
    6: "6th",
    7: "last",
}

SMILEYS: dict[int, str] = {
    0: "off",
    1: "standard",
    2: "special 2",
    3: "special 3",
    4: "special 4",
    5: "special 5",
    6: "special 6",
    7: "special 7",
    8: "special 8",
    9: "special 9",
    10: "special 10",
    11: "special 11",
}


def mode_name(protocol: int | None, value: int | None) -> str | None:
    """Return a human readable mode for a protocol/value pair."""
    if value is None:
        return None
    table = MODES_V006 if (protocol or 0) >= PROTOCOL_V006 else MODES_LEGACY
    return table.get(value, f"unknown ({value})")


def protocol_name(protocol: int | None) -> str | None:
    """Return a printable protocol version."""
    if protocol is None:
        return None
    return f"V{protocol:03d}"


# ---------------------------------------------------------------------------
# Advertisement
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Advertisement:
    """Decoded Oral-B manufacturer advertisement."""

    protocol: int
    device_type: int
    software_version: int
    state: int
    status: int
    minutes: int
    seconds: int
    mode: int
    progress: int
    quadrant_completion: int
    total_quadrants: int

    @property
    def model(self) -> str:
        return DEVICE_TYPES.get(self.device_type, f"Unknown ({self.device_type})")

    @property
    def sonos_model(self) -> str | None:
        """Sonos sub-model for V008+ (byte 9); None for older protocols."""
        if self.protocol >= PROTOCOL_V008:
            return SONOS_MODELS.get(self.quadrant_completion)
        return None

    @property
    def state_name(self) -> str:
        return STATES.get(self.state, f"unknown ({self.state})")

    @property
    def mode_name(self) -> str:
        return mode_name(self.protocol, self.mode) or "unknown"

    @property
    def brushing_time(self) -> int:
        return self.minutes * 60 + self.seconds

    @property
    def new_sessions(self) -> bool:
        return bool(self.status & 0x02)

    @property
    def power_button(self) -> bool:
        return bool(self.status & 0x08)

    @property
    def mode_button(self) -> bool:
        return bool(self.status & 0x04)

    @property
    def high_pressure(self) -> bool:
        return bool(self.status & 0x80)

    @property
    def pressure_name(self) -> str:
        if self.power_button:
            return "power button pressed"
        if self.mode_button:
            return "mode button pressed"
        return "high" if self.high_pressure else "normal"

    @property
    def quadrant(self) -> str:
        return QUADRANTS.get(self.progress & 0x07, "unknown")

    @property
    def total_quadrants_value(self) -> int:
        return self.total_quadrants & 0x07

    @property
    def smiley(self) -> str:
        return SMILEYS.get((self.progress & 0x38) >> 3, "unknown")

    @property
    def brushing(self) -> bool:
        return self.state == 3


def parse_advertisement(payload: bytes) -> Advertisement | None:
    """Parse the manufacturer payload (company id already stripped).

    Accepts 9..11 byte payloads (the app and the ``oralb-ble`` library both
    see 9 or 11 bytes in practice).  Returns ``None`` for anything that is not
    an Oral-B advertisement.
    """
    if len(payload) < 9:
        return None
    protocol = payload[0]
    if protocol < 1 or protocol > 15:
        # Not an Oral-B advertisement (or a far-future protocol).
        return None
    return Advertisement(
        protocol=protocol,
        device_type=payload[1],
        software_version=payload[2],
        state=payload[3],
        status=payload[4],
        minutes=payload[5],
        seconds=payload[6],
        mode=payload[7],
        progress=payload[8],
        quadrant_completion=payload[9] if len(payload) > 9 else 0,
        total_quadrants=payload[10] if len(payload) > 10 else 0,
    )


# ---------------------------------------------------------------------------
# GATT characteristic parsers
# ---------------------------------------------------------------------------


def parse_device_state(payload: bytes) -> tuple[int, int]:
    """FF04: [state, sub_state]."""
    if len(payload) < 1:
        raise ValueError("empty device state")
    return payload[0], payload[1] if len(payload) > 1 else -1


def parse_button_state(payload: bytes) -> str:
    """FF06: [power_pressed, mode_pressed]."""
    if len(payload) >= 1 and payload[0] == 1:
        return "power pressed"
    if len(payload) >= 2 and payload[1] == 1:
        return "mode pressed"
    return "nothing pressed"


def parse_battery(protocol: int, payload: bytes) -> dict[str, Any]:
    """FF05, protocol dependent (see CharacteristicParser.i)."""
    out: dict[str, Any] = {"level": None, "seconds_left": None}
    if not payload:
        return out
    if protocol <= PROTOCOL_V003:
        out["level"] = payload[0] & 0xFF
        return out
    if protocol <= PROTOCOL_V007:
        if len(payload) < 4:
            return out
        out["level"] = payload[0] & 0x7F
        # V004-V007 store the seconds big-endian (b1 high, b2 low); V008+
        # store them little-endian (b1 low, b2 high).  This asymmetry is in
        # CharacteristicParser.i().
        out["seconds_left"] = ((payload[1] & 0xFF) << 8) | (payload[2] & 0xFF)
        return out
    if len(payload) < 3:
        return out
    out["level"] = payload[0] & 0x7F
    out["seconds_left"] = ((payload[2] & 0xFF) << 8) | (payload[1] & 0xFF)
    if len(payload) >= 5:
        out["voltage_mv"] = payload[3] | (payload[4] << 8)
    if len(payload) >= 7:
        out["current_ma"] = payload[5] | (payload[6] << 8)
    if len(payload) >= 8:
        out["temperature_c"] = payload[7]
    if len(payload) >= 9:
        out["soc_percent"] = payload[8]
    if len(payload) >= 13:
        out["discharge_capacity_mas"] = int.from_bytes(payload[9:13], "little")
    if len(payload) >= 17:
        out["remaining_capacity_mas"] = int.from_bytes(payload[13:17], "little")
    if len(payload) >= 18:
        out["soc_handler_state"] = payload[17]
    return out


def parse_mode(protocol: int, payload: bytes) -> tuple[int | None, str | None]:
    """FF07: one byte mode."""
    if not payload:
        return None, None
    value = payload[0]
    return value, mode_name(protocol, value)


def parse_brushing_time(payload: bytes) -> int | None:
    """FF08: [minutes, seconds]."""
    if len(payload) < 2:
        return None
    return payload[0] * 60 + payload[1]


def parse_quadrant(payload: bytes) -> tuple[str | None, int | None]:
    """FF09: [quadrant, ?, total_quadrants]."""
    if len(payload) < 3:
        return None, None
    q = payload[0] & 0x07
    total = payload[2] & 0x07
    return QUADRANTS.get(q, f"unknown ({q})"), total


def parse_smiley(payload: bytes) -> str | None:
    """FF0A: one byte face id."""
    if not payload:
        return None
    return SMILEYS.get(payload[0], f"unknown ({payload[0]})")


def parse_pressure(protocol: int, payload: bytes) -> dict[str, Any]:
    """FF0B.

    Older protocols: one byte, bit7 = high pressure, bit6 = motor reduced.
    V007+: ten bytes, byte0 = 0 low / 1 normal / 2 high, followed by two
    16-bit little-endian values per record (timestamp/force) and a motor
    target, plus an identifier byte.
    """
    if not payload:
        return {}
    if protocol < PROTOCOL_V007:
        return {
            "state": "high" if payload[0] & 0x80 else "normal",
            "is_high": bool(payload[0] & 0x80),
            "motor_reduced": bool(payload[0] & 0x40),
        }
    state = payload[0]
    out: dict[str, Any] = {
        "state": PRESSURE_STATES.get(state, f"unknown ({state})"),
        "is_high": state == 2,
        "motor_reduced": state == 2,
    }
    if len(payload) >= 10:
        out["record_a_timestamp"] = payload[1] | (payload[2] << 8)
        out["record_a_force"] = payload[3] | (payload[4] << 8)
        out["record_b_timestamp"] = payload[5] | (payload[6] << 8)
        out["record_b_force"] = payload[7] | (payload[8] << 8)
        out["identifier"] = payload[9]
    return out


# ---------------------------------------------------------------------------
# Session data (FF29 selected with Configure READ_DATA)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SessionData:
    """A stored brushing session (CharacteristicParser.z0)."""

    start_time: datetime | None
    duration: int
    on_event_count: int | None
    mode: str | None
    mode_value: int | None
    high_pressure_time: int | None
    low_pressure_time: int | None
    high_pressure_events: int | None
    low_pressure_events: int | None
    average_pressure: int | None
    maximum_pressure: int | None
    last_full_load: datetime | None
    final_battery_level: int | None
    configured_time: int | None
    number_of_sectors: int | None
    session_id: int | None
    user_id: int | None
    tongue_time: int | None
    eco_settings: int | None
    raw: bytes = field(repr=False, default=b"")

    def as_dict(self) -> dict[str, Any]:
        return {
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "duration": self.duration,
            "on_event_count": self.on_event_count,
            "mode": self.mode,
            "mode_value": self.mode_value,
            "high_pressure_time": self.high_pressure_time,
            "low_pressure_time": self.low_pressure_time,
            "high_pressure_events": self.high_pressure_events,
            "low_pressure_events": self.low_pressure_events,
            "average_pressure": self.average_pressure,
            "maximum_pressure": self.maximum_pressure,
            "last_full_load": self.last_full_load.isoformat()
            if self.last_full_load
            else None,
            "final_battery_level": self.final_battery_level,
            "configured_time": self.configured_time,
            "number_of_sectors": self.number_of_sectors,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "tongue_time": self.tongue_time,
            "eco_settings": self.eco_settings,
        }


def _rtc_to_datetime(seconds: int) -> datetime:
    return datetime.fromtimestamp(
        RTC_EPOCH_MS / 1000 + seconds, tz=timezone.utc
    )


def _is_invalid_session(payload: bytes) -> bool:
    if not payload:
        return True
    if all(b == 0x44 for b in payload):
        return True
    if all(b == 0xFF for b in payload):
        return True
    return False


def parse_session(protocol: int, payload: bytes) -> SessionData | None:
    """Parse one FF29 session record for the given protocol."""
    if _is_invalid_session(payload):
        return None
    min_len = 16 if protocol <= PROTOCOL_V006 else (21 if protocol <= PROTOCOL_V008 else 23)
    if len(payload) < min_len:
        return None

    start = _rtc_to_datetime(
        payload[0] | (payload[1] << 8) | (payload[2] << 16) | (payload[3] << 24)
    )

    if protocol == PROTOCOL_V001:
        duration = payload[4] | (payload[5] << 8)
        on_event_count = payload[6]
        mode_value = payload[7]
        high_time = (payload[8] | (payload[9] << 8)) * 10
        high_events = payload[10]
        battery = payload[11]
        last_full = _rtc_to_datetime(
            payload[12]
            | (payload[13] << 8)
            | (payload[14] << 16)
            | (payload[15] << 24)
        )
        return SessionData(
            start_time=start,
            duration=duration,
            on_event_count=on_event_count,
            mode=mode_name(protocol, mode_value),
            mode_value=mode_value,
            high_pressure_time=high_time,
            low_pressure_time=None,
            high_pressure_events=high_events,
            low_pressure_events=None,
            average_pressure=None,
            maximum_pressure=None,
            last_full_load=last_full,
            final_battery_level=battery,
            configured_time=None,
            number_of_sectors=None,
            session_id=None,
            user_id=None,
            tongue_time=None,
            eco_settings=None,
            raw=payload,
        )

    if protocol <= PROTOCOL_V006:
        duration = payload[4] | (payload[5] << 8)
        on_event_count = payload[6]
        mode_value = payload[7]
        high_time = (payload[8] | (payload[9] << 8)) * (
            10 if protocol <= PROTOCOL_V003 else 1
        )
        high_events = payload[10]
        battery = payload[11]
        cfg = payload[12] | (payload[13] << 8)
        sid = payload[14] | (payload[15] << 8)
        return SessionData(
            start_time=start,
            duration=duration,
            on_event_count=on_event_count,
            mode=mode_name(protocol, mode_value),
            mode_value=mode_value,
            high_pressure_time=high_time,
            low_pressure_time=None,
            high_pressure_events=high_events,
            low_pressure_events=None,
            average_pressure=None,
            maximum_pressure=None,
            last_full_load=None,
            final_battery_level=battery,
            configured_time=cfg & 0x1FFF,
            number_of_sectors=(cfg >> 13) & 0x07,
            session_id=sid & 0x1FFF,
            user_id=(sid >> 13) & 0x07,
            tongue_time=None,
            eco_settings=None,
            raw=payload,
        )

    # V007 / V008 / V009
    sid = payload[4] | (payload[5] << 8)
    cfg = payload[6] | (payload[7] << 8)
    duration = payload[8] | (payload[9] << 8)
    high_time = payload[10] | (payload[11] << 8)
    low_time = payload[12] | (payload[13] << 8)
    mode_value = payload[19]
    return SessionData(
        start_time=start,
        duration=duration,
        on_event_count=payload[18],
        mode=mode_name(protocol, mode_value),
        mode_value=mode_value,
        high_pressure_time=high_time,
        low_pressure_time=low_time,
        high_pressure_events=payload[16],
        low_pressure_events=payload[17],
        average_pressure=payload[14],
        maximum_pressure=payload[15],
        last_full_load=None,
        final_battery_level=payload[20],
        configured_time=cfg & 0x1FFF,
        number_of_sectors=(cfg >> 13) & 0x07,
        session_id=sid & 0x1FFF,
        user_id=(sid >> 13) & 0x07,
        tongue_time=payload[21] if len(payload) > 21 else None,
        eco_settings=payload[22] if len(payload) > 22 else None,
        raw=payload,
    )


# ---------------------------------------------------------------------------
# Metadata parsers (FF29 selected with Configure READ_METADATA)
# ---------------------------------------------------------------------------


def parse_ble_controller(payload: bytes) -> dict[str, Any]:
    """CharacteristicParser.r: [6, prefix, number, build, prefix2, n2, b2]."""
    if len(payload) < 4 or payload[0] != 6:
        return {}
    out = {
        "prefix": chr(payload[1]),
        "bootloader": payload[2],
        "bootloader_build": payload[3],
    }
    if len(payload) >= 7:
        out.update(
            {
                "sec_prefix": chr(payload[4]),
                "sec_number": payload[5],
                "sec_build": payload[6],
            }
        )
    return out


def parse_system_controller_1(payload: bytes) -> dict[str, Any]:
    """CharacteristicParser.E0: [7, ?, media, hw_cfg, ?, ?, mem_map, ?, ?, info]."""
    if len(payload) < 10 or payload[0] != 7:
        return {}
    return {
        "media_content_version": payload[2],
        "hardware_configuration": payload[3],
        "memory_map_version": payload[6],
        "info_sector_version": payload[9],
    }


def parse_system_controller_2(payload: bytes) -> dict[str, Any]:
    """CharacteristicParser.F0: second controller version at byte 3."""
    if len(payload) < 4:
        return {}
    return {"second_controller_version": payload[3]}


def parse_hardware_version(payload: bytes) -> int | None:
    """CharacteristicParser.j0: [5, pcba]."""
    if len(payload) >= 2 and payload[0] == 5:
        return payload[1]
    return None


def parse_device_uuid(payload: bytes) -> str | None:
    """CharacteristicParser.h0: 16 raw bytes rendered as a UUID string."""
    if len(payload) < 16:
        return None
    h = payload[:16].hex().upper()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def parse_version_string(payload: bytes) -> str | None:
    """CharacteristicParser.i0: bytes[2].bytes[3].bytes[4]."""
    if len(payload) < 5:
        return None
    return f"{payload[2]}.{payload[3]}.{payload[4]}"


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

# Settings which older protocols prefix with 0x37.
_LEGACY_PREFIXED = {
    CONFIGURE_RTC,
    CONFIGURE_BRUSH_TIMER,
    CONFIGURE_BRUSH_MODES,
    CONFIGURE_QUADRANT_TIMERS,
    CONFIGURE_TONGUE_TIME,
    CONFIGURE_MY_COLOR,
    CONFIGURE_REFILL_REMINDER,
    CONFIGURE_RESET_SETTINGS,
}


def build_configure(setting: int, parameter: int = 0, protocol: int = PROTOCOL_V009) -> bytes:
    """Build a write for the FF21 Configure/Control characteristic.

    This mirrors ``Configure.build()`` in the app.  Note that
    ``READ_METADATA``, ``READ_DATA`` and ``READ_PARAM`` are always direct
    two-byte commands; only the legacy settings are prefixed with 0x37.
    """
    if setting == CONFIGURE_EXTEND_CONNECTION and parameter:
        # 0x31 is shared with REFILL_REMINDER; the seconds byte distinguishes
        # the "extend connection" command from the bare refill selector.
        return bytes((CONFIGURE_EXTEND_CONNECTION, parameter & 0xFF))
    if setting in _LEGACY_PREFIXED:
        if protocol < PROTOCOL_V007:
            return bytes((0x37, setting))
        # New protocols use a bare selector byte; the value is written to the
        # dedicated characteristic afterwards (FF22/FF24/FF25/...).
        return bytes((setting,))
    if setting in (CONFIGURE_READ_PARAM, CONFIGURE_READ_DATA):
        return bytes((setting, parameter & 0xFF))
    if setting == CONFIGURE_READ_METADATA:
        return bytes((CONFIGURE_READ_METADATA, parameter & 0xFF))
    if setting == CONFIGURE_NOTIFICATION_CLEAR:
        return bytes((CONFIGURE_NOTIFICATION_CLEAR, parameter & 0xFF))
    if setting == CONFIGURE_SMART_GUIDE:
        return bytes((CONFIGURE_SMART_GUIDE, parameter & 0xFF))
    if setting == CONFIGURE_START_WEEK_DAY:
        return bytes((CONFIGURE_START_WEEK_DAY, parameter & 0xFF))
    if setting == 0x47:  # ENABLE_FLIGHT_MODE
        return bytes((0x47,))
    if setting == CONFIGURE_PRESSURE:
        return bytes((CONFIGURE_PRESSURE, parameter & 0xFF))
    if setting == CONFIGURE_DASHBOARD:
        return bytes((CONFIGURE_DASHBOARD, parameter & 0xFF))
    if setting in (CONFIGURE_RESET_SETTINGS, 0x34):  # factory reset
        return bytes((setting, 0x52))
    return bytes((setting, parameter & 0xFF))


def build_extend_connection(seconds: int = 255) -> bytes:
    """Ask the brush to keep the connection alive for ``seconds``."""
    return bytes((CONFIGURE_EXTEND_CONNECTION, seconds & 0xFF))


def build_control(command: int, parameter: int = 0) -> bytes:
    """Build a Control (FF21) command.

    From ``Control.build()``:

    * normal commands are ``10 <cmd>``;
    * the four motor-ramping commands are ``2E <cmd>``;
    * tongue-time and pressure-configuration are ``<cmd> <param>`` with no
      namespace prefix.
    """
    if command == CONTROL_SET_MODE:
        return bytes((0x10, parameter & 0xFF))
    if command in (CONTROL_TONGUE_TIME, CONTROL_PRESSURE_CONFIGURATION):
        return bytes((command & 0xFF, parameter & 0xFF))
    if command in (
        CONTROL_DISABLE_ALL_MOTOR_RAMPING,
        CONTROL_ENABLE_SOFT_START_ONLY_MOTOR_RAMPING,
        CONTROL_ENABLE_LOW_CHARGE_ONLY_MOTOR_RAMPING,
        CONTROL_ENABLE_ALL_MOTOR_RAMPING,
    ):
        return bytes((0x2E, command & 0xFF))
    return bytes((0x10, command & 0xFF))


def build_rtc(epoch_ms: int) -> bytes:
    """FF22: little-endian seconds since 2000-01-01."""
    seconds = int((epoch_ms - RTC_EPOCH_MS) / 1000)
    return seconds.to_bytes(4, "little", signed=False)


def build_timezone(offset_minutes: int) -> bytes:
    """FF23: 15-minute units, four per hour."""
    value = (offset_minutes // 60) * 4 + ((offset_minutes % 60) // 15)
    return bytes(((value + 256) % 256,))


def parse_rtc(payload: bytes) -> datetime | None:
    if len(payload) < 4:
        return None
    seconds = int.from_bytes(payload[:4], "little")
    return _rtc_to_datetime(seconds)


def access_control_payload() -> bytes:
    return ACCESS_CONTROL_KEY
