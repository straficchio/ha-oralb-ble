"""BLE transport for Oral-B toothbrushes.

This wraps bleak with the small amount of Oral-B specific sequencing that the
official app performs:

* optionally unlock protected characteristics by writing ``MGS`` to FF10,
* extend the connection time (FF21 ``0x31``),
* select a value with FF21 and read it from FF29,
* read the live characteristics (FF04..FF0B).

Everything is serialized with a lock; a brush accepts one connection at a
time and the official app also queues its GATT operations.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from bleak import BleakClient, BleakError
from bleak.exc import BleakCharacteristicNotFoundError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant

from . import const as c
from .const import (
    CHAR_ACCESS_CONTROL,
    CHAR_BATTERY,
    CHAR_BRUSHING_TIME,
    CHAR_BUTTON,
    CHAR_CONFIGURE,
    CHAR_DEVICE_STATE,
    CHAR_MODE,
    CHAR_MODEL_ID,
    CHAR_PRESSURE,
    CHAR_QUADRANT,
    CHAR_RTC,
    CHAR_SELECTED_DATA,
    CHAR_SMILEY,
    CHAR_TIMEZONE,
    CONFIGURE_READ_DATA,
    CONFIGURE_READ_METADATA,
    CONFIGURE_READ_PARAM,
    DATA_SW_VERSION_MAIN,
    DATA_SW_VERSION_SECONDARY,
    METADATA_DEVICE_PCBA,
    METADATA_DEVICE_UUID,
    METADATA_SW_BLE_CONTROLLER,
    METADATA_SW_SYSTEM_CONTROLLER_1,
    METADATA_SW_SYSTEM_CONTROLLER_2,
    SESSION_SCAN_MISSES,
    SESSION_SLOTS_NEW,
    SESSION_SLOTS_OLD,
)
from .protocol import (
    SessionData,
    build_configure,
    build_extend_connection,
    build_rtc,
    build_timezone,
    parse_battery,
    parse_ble_controller,
    parse_brushing_time,
    parse_button_state,
    parse_device_state,
    parse_device_uuid,
    parse_hardware_version,
    parse_mode,
    parse_pressure,
    parse_quadrant,
    parse_session,
    parse_smiley,
    parse_system_controller_1,
    parse_system_controller_2,
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 25
READ_TIMEOUT = 15
SESSION_READ_TIMEOUT = 120


class OralBConnectionError(Exception):
    """Raised when the brush cannot be reached."""


class OralBClient:
    """A short-lived GATT session with an Oral-B brush."""

    def __init__(self, hass: HomeAssistant, address: str, name: str | None = None) -> None:
        self.hass = hass
        self.address = address
        self.name = name or address
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._disconnected = asyncio.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self, *, pair: bool = False) -> None:
        """Connect to the brush, optionally attempting bonding."""
        async with self._lock:
            if self._client is not None and self._client.is_connected:
                return
            device = async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if device is None:
                raise OralBConnectionError(
                    f"{self.address} is not currently reachable by any Bluetooth adapter"
                )
            self._disconnected.clear()

            def _on_disconnect(_client: BleakClient) -> None:
                self._disconnected.set()

            try:
                self._client = await establish_connection(
                    BleakClientWithServiceCache,
                    device,
                    self.name,
                    disconnected_callback=_on_disconnect,
                    max_attempts=3,
                    timeout=CONNECT_TIMEOUT,
                    pair=pair,
                )
            except (BleakError, TimeoutError, OSError) as err:
                self._client = None
                raise OralBConnectionError(str(err)) from err
            _LOGGER.debug("Connected to Oral-B %s", self.address)

    async def disconnect(self) -> None:
        """Disconnect if connected."""
        async with self._lock:
            client, self._client = self._client, None
            if client is None:
                return
            try:
                await client.disconnect()
            except (BleakError, OSError):
                _LOGGER.debug("Error while disconnecting %s", self.address, exc_info=True)

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    # ------------------------------------------------------------------
    # Low level I/O
    # ------------------------------------------------------------------

    async def _read(self, uuid: str, *, timeout: float = READ_TIMEOUT) -> bytes | None:
        client = self._client
        if client is None:
            raise OralBConnectionError("not connected")
        try:
            return bytes(
                await asyncio.wait_for(client.read_gatt_char(uuid), timeout=timeout)
            )
        except BleakCharacteristicNotFoundError:
            _LOGGER.debug("%s has no characteristic %s", self.address, uuid)
            return None
        except (BleakError, TimeoutError, OSError) as err:
            raise OralBConnectionError(str(err)) from err

    async def _write(
        self, uuid: str, data: bytes, *, response: bool = True, timeout: float = READ_TIMEOUT
    ) -> None:
        client = self._client
        if client is None:
            raise OralBConnectionError("not connected")
        try:
            await asyncio.wait_for(
                client.write_gatt_char(uuid, data, response=response), timeout=timeout
            )
        except BleakCharacteristicNotFoundError:
            _LOGGER.debug("%s has no characteristic %s", self.address, uuid)
        except (BleakError, TimeoutError, OSError) as err:
            raise OralBConnectionError(str(err)) from err

    async def _select_and_read(
        self, setting: int, parameter: int, protocol: int, *, timeout: float = READ_TIMEOUT
    ) -> bytes | None:
        """Write a Configure selector to FF21 and read FF29."""
        await self._write(CHAR_CONFIGURE, build_configure(setting, parameter, protocol))
        # The firmware copies the selected value asynchronously; the app's
        # command queue also yields between the write and the read.
        await asyncio.sleep(0.08)
        return await self._read(CHAR_SELECTED_DATA, timeout=timeout)

    # ------------------------------------------------------------------
    # Oral-B specific helpers
    # ------------------------------------------------------------------

    async def read_protocol(self) -> int | None:
        """Read the protocol version from FF02 when no advertisement is known."""
        payload = await self._read(CHAR_MODEL_ID)
        if payload and len(payload) >= 2 and 1 <= payload[1] <= 9:
            return payload[1]
        return None

    async def unlock(self, protocol: int) -> None:
        """Unlock protected characteristics on V007+ firmware."""
        if protocol >= 8:
            await self._write(CHAR_ACCESS_CONTROL, b"MGS")

    async def extend_connection(self, seconds: int = 255) -> None:
        """Ask the brush not to drop the link while we sync sessions."""
        await self._write(CHAR_CONFIGURE, build_extend_connection(seconds))

    async def update_read_params(self, protocol: int) -> None:
        """V001-V006 need a READ_PARAM(0) write before reading values."""
        if protocol < 8:
            await self._write(CHAR_CONFIGURE, build_configure(CONFIGURE_READ_PARAM, 0, protocol))

    async def _read_optional(self, uuid: str) -> bytes | None:
        """Read a characteristic, tolerating firmware that lacks it."""
        try:
            return await self._read(uuid)
        except OralBConnectionError as err:
            _LOGGER.debug("Optional read %s failed on %s: %s", uuid, self.address, err)
            return None

    async def read_live(self, protocol: int) -> dict[str, Any]:
        """Read the live characteristics that the advertisement does not carry."""
        out: dict[str, Any] = {}

        state = await self._read_optional(CHAR_DEVICE_STATE)
        if state:
            out["state"], out["sub_state"] = parse_device_state(state)

        battery = await self._read_optional(CHAR_BATTERY)
        if battery:
            out["battery"] = parse_battery(protocol, battery)

        button = await self._read_optional(CHAR_BUTTON)
        if button:
            out["button"] = parse_button_state(button)

        mode = await self._read_optional(CHAR_MODE)
        if mode:
            out["mode_value"], out["mode"] = parse_mode(protocol, mode)

        brushing_time = await self._read_optional(CHAR_BRUSHING_TIME)
        if brushing_time:
            out["brushing_time"] = parse_brushing_time(brushing_time)

        quadrant = await self._read_optional(CHAR_QUADRANT)
        if quadrant:
            out["quadrant"], out["total_quadrants"] = parse_quadrant(quadrant)

        smiley = await self._read_optional(CHAR_SMILEY)
        if smiley:
            out["smiley"] = parse_smiley(smiley)

        pressure = await self._read_optional(CHAR_PRESSURE)
        if pressure:
            out["pressure"] = parse_pressure(protocol, pressure)

        return out

    async def read_metadata(self, protocol: int, metadata: int) -> bytes | None:
        """Read one metadata selector from FF29."""
        return await self._select_and_read(
            CONFIGURE_READ_METADATA, metadata, protocol
        )

    async def read_metadata_bundle(self, protocol: int) -> dict[str, Any]:
        """Read the metadata the app uses to identify a brush."""
        out: dict[str, Any] = {}

        ble = await self.read_metadata(protocol, METADATA_SW_BLE_CONTROLLER)
        if ble:
            out.update(parse_ble_controller(ble))

        sys1 = await self.read_metadata(protocol, METADATA_SW_SYSTEM_CONTROLLER_1)
        if sys1:
            out.update(parse_system_controller_1(sys1))

        sys2 = await self.read_metadata(protocol, METADATA_SW_SYSTEM_CONTROLLER_2)
        if sys2:
            out.update(parse_system_controller_2(sys2))

        pcba = await self.read_metadata(protocol, METADATA_DEVICE_PCBA)
        if pcba:
            hw = parse_hardware_version(pcba)
            if hw is not None:
                out["hardware_version"] = hw

        uuid = await self.read_metadata(protocol, METADATA_DEVICE_UUID)
        if uuid:
            out["device_uuid"] = parse_device_uuid(uuid)

        main_ver = await self._select_and_read(
            CONFIGURE_READ_DATA, DATA_SW_VERSION_MAIN, protocol
        )
        if main_ver and len(main_ver) >= 5:
            out["main_firmware"] = f"{main_ver[2]}.{main_ver[3]}.{main_ver[4]}"

        sec_ver = await self._select_and_read(
            CONFIGURE_READ_DATA, DATA_SW_VERSION_SECONDARY, protocol
        )
        if sec_ver and len(sec_ver) >= 5:
            out["secondary_firmware"] = f"{sec_ver[2]}.{sec_ver[3]}.{sec_ver[4]}"

        return out

    async def read_session(self, protocol: int, index: int) -> SessionData | None:
        """Read one FF29 session slot."""
        payload = await self._select_and_read(
            CONFIGURE_READ_DATA, index, protocol, timeout=SESSION_READ_TIMEOUT
        )
        if payload is None:
            return None
        return parse_session(protocol, payload)

    async def sync_sessions(
        self,
        protocol: int,
        last_sync_ms: float = 0,
        *,
        max_slots: int | None = None,
        stop_after_old: int = SESSION_SCAN_MISSES,
    ) -> tuple[list[SessionData], datetime | None]:
        """Scan session slots and return sessions newer than ``last_sync_ms``.

        The brush stores sessions in a ring buffer.  The official app scans
        every slot (250 for V006+, 30 for older) and filters by start time.
        We scan a bounded number of slots and stop after a run of slots that
        are invalid or older than the last sync, which keeps a normal poll
        short while still finding a wrapped buffer in most cases.
        """
        slots = max_slots or (SESSION_SLOTS_NEW if protocol >= 6 else SESSION_SLOTS_OLD)
        new_sessions: list[SessionData] = []
        newest: datetime | None = None
        old_run = 0
        seen_valid = False

        for index in range(slots):
            try:
                session = await self.read_session(protocol, index)
            except OralBConnectionError:
                raise
            if session is None:
                old_run += 1
            else:
                seen_valid = True
                if newest is None or (
                    session.start_time is not None and session.start_time > newest
                ):
                    newest = session.start_time
                start_ms = (
                    session.start_time.timestamp() * 1000
                    if session.start_time is not None
                    else 0
                )
                if start_ms > last_sync_ms and session.session_id != 0:
                    new_sessions.append(session)
                    old_run = 0
                else:
                    old_run += 1
            if seen_valid and old_run >= stop_after_old:
                break

        new_sessions.sort(key=lambda s: s.start_time or datetime.min.replace(tzinfo=timezone.utc))
        return new_sessions, newest

    async def clear_notifications(self, protocol: int) -> None:
        """Clear the "new sessions" notification flag (best effort)."""
        try:
            await self._write(
                CHAR_CONFIGURE,
                build_configure(c.CONFIGURE_NOTIFICATION_CLEAR, 0, protocol),
            )
        except OralBConnectionError:
            _LOGGER.debug("Could not clear notifications on %s", self.address)

    async def sync_time(self, protocol: int, tz_offset_minutes: int) -> None:
        """Write RTC and timezone (the app's syncTime sequence)."""
        await self._write(
            CHAR_CONFIGURE, build_configure(c.CONFIGURE_RTC, 0, protocol)
        )
        await self._write(CHAR_RTC, build_rtc(int(datetime.now(tz=timezone.utc).timestamp() * 1000)))
        await self._write(CHAR_TIMEZONE, build_timezone(tz_offset_minutes))
