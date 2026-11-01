"""Protocol tests for the Oral-B BLE integration.

Run with:  python -m pytest tests -q
"""

from __future__ import annotations

from datetime import datetime, timezone


from oralb_ble_test import const as c
from oralb_ble_test import protocol as p


def test_advertisement_from_oralb_ble_docs():
    # Captured advertisement payload used by Bluetooth-Devices/oralb-ble.
    payload = bytes.fromhex("062b6b0272000001010004")
    adv = p.parse_advertisement(payload)
    assert adv is not None
    assert adv.protocol == 6
    assert adv.device_type == 43  # not a known type in the app's table
    assert adv.software_version == 107
    assert adv.state == 2
    assert adv.state_name == "idle"
    assert adv.mode == 1
    assert adv.mode_name == "sensitive"
    assert adv.brushing_time == 0
    assert adv.total_quadrants_value == 4
    assert adv.new_sessions is True
    assert adv.pressure_name == "normal"


def test_advertisement_known_model():
    # protocol 8, type 0x35 (iO5), sw 0x2a, running, status 0x82
    payload = bytes([8, 0x35, 0x2A, 3, 0x82, 1, 30, 2, 0x02, 0, 4])
    adv = p.parse_advertisement(payload)
    assert adv is not None
    assert adv.model == "Oral-B iO5"
    assert adv.state_name == "running"
    assert adv.brushing is True
    assert adv.brushing_time == 90
    assert adv.quadrant == "2nd"
    assert adv.smiley == "off"
    assert adv.pressure_name == "high"
    assert adv.new_sessions is True


def test_advertisement_rejects_garbage():
    assert p.parse_advertisement(b"") is None
    assert p.parse_advertisement(b"\x00" * 9) is None
    assert p.parse_advertisement(bytes([99]) + b"\x00" * 10) is None


def test_device_state():
    assert p.parse_device_state(b"\x03\x00") == (3, 0)
    assert p.parse_device_state(b"\x02") == (2, -1)


def test_battery_v008():
    payload = bytes([0x50, 0x10, 0x00, 0x2C, 0x01])
    out = p.parse_battery(8, payload)
    assert out["level"] == 80
    assert out["seconds_left"] == 16
    assert out["voltage_mv"] == 300


def test_battery_legacy():
    assert p.parse_battery(2, b"\x64")["level"] == 100
    out = p.parse_battery(5, bytes([0x80, 0x00, 0x10, 0x00]))
    assert out["level"] == 0  # 0x80 & 0x7F
    assert out["seconds_left"] == 16


def test_brushing_time_and_mode():
    assert p.parse_brushing_time(b"\x01\x1e") == 90
    assert p.parse_mode(4, b"\x04") == (4, "whitening")
    assert p.parse_mode(8, b"\x01") == (1, "sensitive")
    assert p.parse_mode(8, b"\x0b") == (11, "smart adapt")


def test_quadrant_and_smiley():
    assert p.parse_quadrant(b"\x02\x00\x04") == ("2nd", 4)
    assert p.parse_smiley(b"\x01") == "standard"
    # progress 0b00010010 -> quadrant 2, smiley 2
    adv = p.parse_advertisement(bytes([8, 0x35, 1, 3, 0, 0, 0, 0, 0x12, 0, 4]))
    assert adv is not None
    assert adv.quadrant == "2nd"
    assert adv.smiley == "special 2"


def test_pressure_legacy_and_new():
    assert p.parse_pressure(5, b"\x80")["state"] == "high"
    assert p.parse_pressure(5, b"\x40")["motor_reduced"] is True
    payload = bytes([2, 1, 0, 2, 0, 3, 0, 4, 0, 9])
    out = p.parse_pressure(8, payload)
    assert out["state"] == "high"
    assert out["record_a_timestamp"] == 1
    assert out["record_a_force"] == 2
    assert out["record_b_timestamp"] == 3
    assert out["record_b_force"] == 4
    assert out["identifier"] == 9


def _session_v008() -> bytes:
    sid = 5 | (2 << 13)
    cfg = 120 | (4 << 13)
    return (
        (0).to_bytes(4, "little")
        + sid.to_bytes(2, "little")
        + cfg.to_bytes(2, "little")
        + (120).to_bytes(2, "little")
        + (10).to_bytes(2, "little")
        + (5).to_bytes(2, "little")
        + bytes([1, 2, 3, 4, 5, 1, 80])
    )


def test_session_v008():
    session = p.parse_session(8, _session_v008())
    assert session is not None
    assert session.start_time == datetime(2000, 1, 1, tzinfo=timezone.utc)
    assert session.duration == 120
    assert session.session_id == 5
    assert session.user_id == 2
    assert session.configured_time == 120
    assert session.number_of_sectors == 4
    assert session.high_pressure_time == 10
    assert session.low_pressure_time == 5
    assert session.average_pressure == 1
    assert session.maximum_pressure == 2
    assert session.high_pressure_events == 3
    assert session.low_pressure_events == 4
    assert session.on_event_count == 5
    assert session.mode == "sensitive"
    assert session.final_battery_level == 80


def test_session_invalid():
    assert p.parse_session(8, b"") is None
    assert p.parse_session(8, b"\x44" * 21) is None
    assert p.parse_session(8, b"\xff" * 21) is None
    assert p.parse_session(8, b"\x00" * 10) is None


def test_configure_builders():
    assert p.build_configure(p.CONFIGURE_READ_METADATA, 1, 9) == b"\x05\x01"
    assert p.build_configure(p.CONFIGURE_READ_DATA, 0, 9) == b"\x02\x00"
    assert p.build_configure(p.CONFIGURE_READ_PARAM, 0, 6) == b"\x01\x00"
    assert p.build_configure(p.CONFIGURE_RTC, 0, 9) == b"\x26"
    assert p.build_configure(p.CONFIGURE_RTC, 0, 6) == b"\x37\x26"
    assert p.build_configure(p.CONFIGURE_REFILL_REMINDER, 0, 9) == b"\x31"
    assert p.build_configure(p.CONFIGURE_REFILL_REMINDER, 0, 6) == b"\x37\x31"
    assert p.build_extend_connection(255) == b"\x31\xff"
    assert p.build_configure(p.CONFIGURE_EXTEND_CONNECTION, 255, 9) == b"\x31\xff"
    assert p.build_control(c.CONTROL_MY_COLOR_ENABLE) == b"\x10\x31"
    assert p.build_control(c.CONTROL_SET_MODE, 4) == b"\x10\x04"
    assert p.build_control(c.CONTROL_TONGUE_TIME, 30) == b"\x2b\x1e"
    assert p.build_control(c.CONTROL_DISABLE_ALL_MOTOR_RAMPING) == b"\x2e\x00"
    assert p.build_control(c.CONTROL_ENABLE_ALL_MOTOR_RAMPING) == b"\x2e\x03"


def test_rtc_roundtrip():
    now = int(datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
    encoded = p.build_rtc(now)
    assert len(encoded) == 4
    decoded = p.parse_rtc(encoded)
    assert decoded is not None
    assert int(decoded.timestamp()) == now // 1000


def test_timezone():
    assert p.build_timezone(0) == b"\x00"
    assert p.build_timezone(60) == b"\x04"
    assert p.build_timezone(90) == b"\x06"
    assert p.build_timezone(-300) == bytes([0xEC])
