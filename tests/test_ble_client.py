"""Mocked GATT tests for OralBClient."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from custom_components.oralb_ble import const as c
from custom_components.oralb_ble.ble import OralBClient


class FakeClient:
    """Minimal bleak client double."""

    def __init__(self) -> None:
        self.is_connected = True
        self.writes: list[tuple[str, bytes]] = []
        self.reads: list[str] = []
        self.session_index = 0

    async def read_gatt_char(self, uuid: str) -> bytes:
        self.reads.append(uuid)
        if uuid == c.CHAR_DEVICE_STATE:
            return b"\x03\x00"
        if uuid == c.CHAR_BATTERY:
            return bytes([0x50, 0x10, 0x00, 0x2C, 0x01])
        if uuid == c.CHAR_BUTTON:
            return b"\x00\x00"
        if uuid == c.CHAR_MODE:
            return b"\x01"
        if uuid == c.CHAR_BRUSHING_TIME:
            return b"\x01\x1E"
        if uuid == c.CHAR_QUADRANT:
            return b"\x02\x00\x04"
        if uuid == c.CHAR_SMILEY:
            return b"\x01"
        if uuid == c.CHAR_PRESSURE:
            return bytes([1, 1, 0, 2, 0, 3, 0, 4, 0, 9])
        if uuid == c.CHAR_SELECTED_DATA:
            # Return a session record for READ_DATA(0), otherwise metadata.
            last = self.writes[-1][1] if self.writes else b""
            if last.startswith(bytes([c.CONFIGURE_READ_DATA])):
                index = last[1]
                if index == 0:
                    return _session()
                if index == 1:
                    return b"\x44" * 21
                if index == c.DATA_SW_VERSION_MAIN:
                    return bytes([0, 0, 1, 2, 3])
                if index == c.DATA_SW_VERSION_SECONDARY:
                    return bytes([0, 0, 4, 5, 6])
            if last.startswith(bytes([c.CONFIGURE_READ_METADATA])):
                selector = last[1]
                if selector == c.METADATA_SW_BLE_CONTROLLER:
                    return bytes([6, ord("A"), 3, 4, ord("B"), 5, 6])
                if selector == c.METADATA_SW_SYSTEM_CONTROLLER_1:
                    return bytes([7, 0, 12, 1, 0, 0, 1, 0, 0, 0])
                if selector == c.METADATA_SW_SYSTEM_CONTROLLER_2:
                    return bytes([0, 0, 0, 0x21])
                if selector == c.METADATA_DEVICE_PCBA:
                    return bytes([5, 0x0C])
                if selector == c.METADATA_DEVICE_UUID:
                    return bytes(range(16))
        raise AssertionError(f"unexpected read {uuid}")

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool = True) -> None:
        self.writes.append((uuid, bytes(data)))

    async def disconnect(self) -> None:
        self.is_connected = False


def _session() -> bytes:
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


@pytest.mark.asyncio
async def test_read_live_and_metadata(hass):
    fake = FakeClient()
    client = OralBClient(hass, "78:DB:2F:C2:48:BE", "Test")

    with patch(
        "custom_components.oralb_ble.ble.async_ble_device_from_address",
        return_value=object(),
    ), patch(
        "custom_components.oralb_ble.ble.establish_connection",
        return_value=fake,
    ) as connect:
        await client.connect(pair=True)
        connect.assert_awaited_once()
        assert connect.await_args.kwargs["pair"] is True
        live = await client.read_live(8)
        meta = await client.read_metadata_bundle(8)
        await client.disconnect()

    assert live["state"] == 3
    assert live["battery"]["level"] == 80
    assert live["battery"]["seconds_left"] == 16
    assert live["mode"] == "sensitive"
    assert live["brushing_time"] == 90
    assert live["quadrant"] == "2nd"
    assert live["smiley"] == "standard"
    assert live["pressure"]["state"] == "normal"

    assert meta["prefix"] == "A"
    assert meta["bootloader"] == 3
    assert meta["bootloader_build"] == 4
    assert meta["sec_number"] == 5
    assert meta["hardware_version"] == 0x0C
    assert meta["device_uuid"] == "00010203-0405-0607-0809-0A0B0C0D0E0F"
    assert meta["second_controller_version"] == 0x21


@pytest.mark.asyncio
async def test_sync_sessions(hass):
    fake = FakeClient()
    client = OralBClient(hass, "78:DB:2F:C2:48:BE", "Test")

    with patch(
        "custom_components.oralb_ble.ble.async_ble_device_from_address",
        return_value=object(),
    ), patch(
        "custom_components.oralb_ble.ble.establish_connection",
        return_value=fake,
    ):
        await client.connect()
        sessions, newest = await client.sync_sessions(8, 0, max_slots=2, stop_after_old=2)
        await client.disconnect()

    assert len(sessions) == 1
    assert sessions[0].session_id == 5
    assert sessions[0].duration == 120
    assert newest is not None
