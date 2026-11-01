"""Data model for the Oral-B BLE integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .protocol import Advertisement, SessionData


@dataclass
class OralBData:
    """Everything we know about one brush."""

    address: str
    name: str

    # Identity
    model: str | None = None
    protocol: int | None = None
    software_version: int | None = None
    device_uuid: str | None = None
    hardware_version: int | None = None

    # Live state
    state: str | None = None
    state_raw: int | None = None
    sub_state: int | None = None
    battery: int | None = None
    battery_seconds_left: int | None = None
    battery_voltage_mv: int | None = None
    battery_temperature_c: int | None = None
    mode: str | None = None
    mode_value: int | None = None
    brushing_time: int | None = None
    quadrant: str | None = None
    total_quadrants: int | None = None
    pressure: str | None = None
    smiley: str | None = None
    button: str | None = None
    new_sessions: bool = False
    rssi: int | None = None

    # Firmware / hardware metadata
    firmware: str | None = None
    bootloader: str | None = None
    secondary_firmware: str | None = None
    media_content_version: int | None = None
    hardware_configuration: int | None = None
    memory_map_version: int | None = None
    info_sector_version: int | None = None
    second_controller_version: int | None = None

    # Session history
    last_session: SessionData | None = None
    recent_sessions: list[dict] = field(default_factory=list)
    sessions_today: int = 0
    total_sessions: int = 0
    last_sync: datetime | None = None

    # Liveness
    last_seen: datetime | None = None
    last_gatt_poll: datetime | None = None
    connected: bool = False

    @property
    def sector_index(self) -> int | None:
        """Numeric sector index: 0 none, 1-6 first-sixth, 7 last."""
        return {
            "none": 0,
            "1st": 1,
            "2nd": 2,
            "3rd": 3,
            "4th": 4,
            "5th": 5,
            "6th": 6,
            "last": 7,
        }.get(self.quadrant)

    @property
    def brushing(self) -> bool:
        return self.state_raw == 3

    @property
    def charging(self) -> bool:
        return self.state_raw == 4

    def apply_advertisement(self, adv: Advertisement, rssi: int, seen: datetime) -> None:
        """Merge a passive advertisement into the current state."""
        self.protocol = adv.protocol
        self.model = adv.model
        self.software_version = adv.software_version
        self.state_raw = adv.state
        self.state = adv.state_name
        self.mode_value = adv.mode
        self.mode = adv.mode_name
        self.brushing_time = adv.brushing_time
        self.quadrant = adv.quadrant
        self.total_quadrants = adv.total_quadrants_value
        self.pressure = adv.pressure_name
        self.smiley = adv.smiley
        self.new_sessions = adv.new_sessions
        self.rssi = rssi
        self.last_seen = seen
        self.connected = False
