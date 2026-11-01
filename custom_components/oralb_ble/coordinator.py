"""Coordinator for the Oral-B BLE integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .ble import OralBClient, OralBConnectionError
from .const import (
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SESSION_SYNC,
    DOMAIN,
    SESSION_SLOTS_NEW,
    SESSION_SLOTS_OLD,
)
from .models import OralBData
from .protocol import Advertisement, parse_advertisement

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
MAX_RECENT_SESSIONS = 100


class OralBSessionStore:
    """Persist last-sync state and the recent session list."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{address}")
        self.last_sync: datetime | None = None
        self.known_sessions: set[str] = set()
        self.recent_sessions: list[dict[str, Any]] = []
        self.total_sessions: int = 0
        self.initial_scan_done: bool = False

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        if last := data.get("last_sync"):
            try:
                self.last_sync = datetime.fromisoformat(last)
            except ValueError:
                self.last_sync = None
        self.known_sessions = set(data.get("known_sessions", []))
        self.recent_sessions = list(data.get("recent_sessions", []))
        self.total_sessions = int(data.get("total_sessions", 0))
        self.initial_scan_done = bool(data.get("initial_scan_done", False))

    async def async_save(self) -> None:
        await self._store.async_save(
            {
                "last_sync": self.last_sync.isoformat() if self.last_sync else None,
                "known_sessions": sorted(self.known_sessions)[-500:],
                "recent_sessions": self.recent_sessions[-MAX_RECENT_SESSIONS:],
                "total_sessions": self.total_sessions,
                "initial_scan_done": self.initial_scan_done,
            }
        )


class OralBCoordinator(DataUpdateCoordinator[OralBData]):
    """Poll a brush and ingest its advertisements."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        address: str,
        name: str,
        initial: OralBData | None = None,
    ) -> None:
        interval_minutes = int(
            entry.options.get("poll_interval", DEFAULT_POLL_INTERVAL.total_seconds() / 60)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {address}",
            update_interval=timedelta(minutes=interval_minutes),
        )
        self.address = address
        self._name = name
        self._store = OralBSessionStore(hass, address)
        self._sync_lock = asyncio.Lock()
        self._pending_sync: asyncio.TimerHandle | None = None
        self._last_gatt_metadata: datetime | None = None
        self._last_advertisement: Advertisement | None = None
        self._previous_state: int | None = None
        self.data = initial or OralBData(address=address, name=name)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        await self._store.async_load()
        if self._store.last_sync:
            self.data.last_sync = self._store.last_sync
        self.data.recent_sessions = list(self._store.recent_sessions)
        self.data.total_sessions = self._store.total_sessions
        self._recompute_today()

    def _recompute_today(self) -> None:
        today = dt_util.now().date()
        count = 0
        for session in self.data.recent_sessions:
            start = session.get("start_time")
            if not start:
                continue
            try:
                if datetime.fromisoformat(start).astimezone().date() == today:
                    count += 1
            except ValueError:
                continue
        self.data.sessions_today = count

    # ------------------------------------------------------------------
    # Passive advertisement path
    # ------------------------------------------------------------------

    @callback
    def async_handle_advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: Any = None
    ) -> None:
        """Merge a BLE advertisement; called for every matching packet."""
        payload = service_info.manufacturer_data.get(0x00DC)
        if not payload:
            return
        adv = parse_advertisement(payload)
        if adv is None:
            return

        previous_state = self.data.state_raw
        self.data.apply_advertisement(adv, service_info.rssi, dt_util.utcnow())
        self._last_advertisement = adv
        if self.data.protocol is None:
            self.data.protocol = adv.protocol

        # A brushing session just ended and the brush says it has new data:
        # give the firmware a few seconds to finalise the record, then sync.
        if (
            previous_state == 3
            and adv.state != 3
            and adv.new_sessions
            and self.config_entry.options.get("session_sync", DEFAULT_SESSION_SYNC)
        ):
            self._schedule_session_sync(20)

        self.async_set_updated_data(self.data)

    def _schedule_session_sync(self, delay: int) -> None:
        if self._pending_sync is not None:
            self._pending_sync.cancel()
        self._pending_sync = self.hass.loop.call_later(
            delay, lambda: self.hass.async_create_task(self.async_sync_sessions())
        )

    # ------------------------------------------------------------------
    # Active GATT path
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> OralBData:
        """Poll the brush over GATT.

        Advertisements already provide live state, so we avoid connecting
        while the brush is running.  A sleeping brush is not an error: the
        last known data stays available.
        """
        if self.data.state_raw == 3:
            _LOGGER.debug("%s is brushing; skipping GATT poll", self.address)
            return self.data

        if self.data.last_seen is None or (
            dt_util.utcnow() - self.data.last_seen > timedelta(minutes=10)
        ):
            # Not seen recently; try anyway (a wake-up may have been missed)
            # but do not mark the entry as failed.
            _LOGGER.debug("%s has not advertised recently", self.address)

        client = OralBClient(self.hass, self.address, self._name)
        try:
            await client.connect(
                pair=self.config_entry.options.get("pair_on_connect", False)
            )
            if self.data.protocol is None:
                detected = await client.read_protocol()
                if detected is not None:
                    self.data.protocol = detected
            protocol = self.data.protocol or 9
            await client.unlock(protocol)
            await client.extend_connection(255)
            await client.update_read_params(protocol)

            live = await client.read_live(protocol)
            self._apply_live(live)

            now = dt_util.utcnow()
            if self._last_gatt_metadata is None or now - self._last_gatt_metadata > timedelta(
                hours=24
            ):
                try:
                    meta = await client.read_metadata_bundle(protocol)
                    self._apply_metadata(meta)
                    self._last_gatt_metadata = now
                except OralBConnectionError as err:
                    _LOGGER.debug("Metadata read failed for %s: %s", self.address, err)

            if self.config_entry.options.get("session_sync", DEFAULT_SESSION_SYNC):
                # A full 250-slot scan is only needed when the brush says it
                # has new data (or on the first run).  Other polls do a short
                # 20-slot catch-up scan.
                full = self.data.new_sessions or not self._store.initial_scan_done
                await self._sync_sessions_locked(
                    client,
                    protocol,
                    full=full,
                    fire_events=self._store.initial_scan_done,
                )

            self.data.connected = True
            self.data.last_gatt_poll = now
        except OralBConnectionError as err:
            _LOGGER.debug("GATT poll failed for %s: %s", self.address, err)
            # Do not raise: a sleeping brush is normal and entities keep their
            # last known values.
        finally:
            await client.disconnect()
            self.data.connected = False

        return self.data

    def _apply_live(self, live: dict[str, Any]) -> None:
        if "state" in live:
            self.data.state_raw = live["state"]
            self.data.sub_state = live.get("sub_state")
            from .protocol import STATES

            self.data.state = STATES.get(live["state"], f"unknown ({live['state']})")
        if battery := live.get("battery"):
            self.data.battery = battery.get("level")
            self.data.battery_seconds_left = battery.get("seconds_left")
            self.data.battery_voltage_mv = battery.get("voltage_mv")
            self.data.battery_temperature_c = battery.get("temperature_c")
        if "button" in live:
            self.data.button = live["button"]
        if "mode" in live:
            self.data.mode = live["mode"]
            self.data.mode_value = live.get("mode_value")
        if "brushing_time" in live:
            self.data.brushing_time = live["brushing_time"]
        if "quadrant" in live:
            self.data.quadrant = live["quadrant"]
            self.data.total_quadrants = live.get("total_quadrants")
        if "smiley" in live:
            self.data.smiley = live["smiley"]
        if "pressure" in live:
            self.data.pressure = live["pressure"].get("state")

    def _apply_metadata(self, meta: dict[str, Any]) -> None:
        if "bootloader" in meta:
            prefix = meta.get("prefix", "")
            self.data.bootloader = f"{prefix}{meta['bootloader']}.{meta['bootloader_build']}"
        if "sec_number" in meta:
            prefix = meta.get("sec_prefix", "")
            self.data.secondary_firmware = f"{prefix}{meta['sec_number']}.{meta['sec_build']}"
        if "main_firmware" in meta:
            self.data.firmware = meta["main_firmware"]
        if "hardware_version" in meta:
            self.data.hardware_version = meta["hardware_version"]
        if "device_uuid" in meta:
            self.data.device_uuid = meta["device_uuid"]
        for key in (
            "media_content_version",
            "hardware_configuration",
            "memory_map_version",
            "info_sector_version",
            "second_controller_version",
        ):
            if key in meta:
                setattr(self.data, key, meta[key])

    async def _sync_sessions_locked(
        self,
        client: OralBClient,
        protocol: int,
        *,
        full: bool = False,
        fire_events: bool = True,
    ) -> None:
        """Serialize session syncs so a button and a scheduled sync cannot race."""
        if self._sync_lock.locked():
            return
        async with self._sync_lock:
            await self._sync_sessions(
                client, protocol, full=full, fire_events=fire_events
            )

    async def _sync_sessions(
        self,
        client: OralBClient,
        protocol: int,
        *,
        full: bool = False,
        fire_events: bool = True,
    ) -> None:
        last_sync_ms = (
            self._store.last_sync.timestamp() * 1000 if self._store.last_sync else 0
        )
        configured_slots = int(
            self.config_entry.options.get(
                "session_slots",
                SESSION_SLOTS_NEW if protocol >= 6 else SESSION_SLOTS_OLD,
            )
        )
        max_slots = configured_slots if full else min(configured_slots, 20)
        sessions, newest = await client.sync_sessions(
            protocol,
            last_sync_ms,
            max_slots=max_slots,
            stop_after_old=max_slots if full else 5,
        )

        fired = 0
        for session in sessions:
            key = f"{session.session_id}:{session.start_time.isoformat() if session.start_time else ''}"
            if key in self._store.known_sessions:
                continue
            self._store.known_sessions.add(key)
            self._store.total_sessions += 1
            self._store.recent_sessions.append(session.as_dict())
            fired += 1
            if fire_events:
                self.hass.bus.async_fire(
                    f"{DOMAIN}_session",
                    {
                        "address": self.address,
                        "name": self.data.name,
                        "session": session.as_dict(),
                    },
                )

        self._store.recent_sessions.sort(key=lambda item: item.get("start_time") or "")
        self._store.recent_sessions = self._store.recent_sessions[-MAX_RECENT_SESSIONS:]
        self.data.recent_sessions = list(self._store.recent_sessions)
        self.data.total_sessions = self._store.total_sessions
        if self.data.recent_sessions:
            last = self.data.recent_sessions[-1]
            # Keep the structured object for the last session sensors.
            self.data.last_session = _dict_to_session(last)

        if newest is not None and (
            self._store.last_sync is None or newest > self._store.last_sync
        ):
            self._store.last_sync = newest
        elif sessions:
            candidate = max(
                (s.start_time for s in sessions if s.start_time),
                default=dt_util.utcnow(),
            )
            if self._store.last_sync is None or candidate > self._store.last_sync:
                self._store.last_sync = candidate
        self.data.last_sync = self._store.last_sync
        self._recompute_today()
        await self._store.async_save()
        if fired:
            _LOGGER.info("Synced %d new session(s) from %s", fired, self.address)
        if full:
            self._store.initial_scan_done = True
            self.data.new_sessions = False
            await client.clear_notifications(protocol)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def async_sync_sessions(self) -> None:
        """Connect and scan session slots (used by the Sync button)."""
        client = OralBClient(self.hass, self.address, self._name)
        try:
            await client.connect(
                pair=self.config_entry.options.get("pair_on_connect", False)
            )
            if self.data.protocol is None:
                detected = await client.read_protocol()
                if detected is not None:
                    self.data.protocol = detected
            protocol = self.data.protocol or 9
            await client.unlock(protocol)
            await client.extend_connection(255)
            await self._sync_sessions_locked(client, protocol, full=True)
            self.async_set_updated_data(self.data)
        except OralBConnectionError as err:
            _LOGGER.warning("Session sync failed for %s: %s", self.address, err)
            raise
        finally:
            await client.disconnect()

    async def async_sync_time(self) -> None:
        """Write the current time and timezone to the brush."""
        client = OralBClient(self.hass, self.address, self._name)
        try:
            await client.connect(
                pair=self.config_entry.options.get("pair_on_connect", False)
            )
            if self.data.protocol is None:
                detected = await client.read_protocol()
                if detected is not None:
                    self.data.protocol = detected
            protocol = self.data.protocol or 9
            await client.unlock(protocol)
            await client.extend_connection(60)
            offset = int(dt_util.now().utcoffset().total_seconds() // 60)
            await client.sync_time(protocol, offset)
        except OralBConnectionError as err:
            _LOGGER.warning("Time sync failed for %s: %s", self.address, err)
            raise
        finally:
            await client.disconnect()


def _dict_to_session(data: dict[str, Any]):
    """Rehydrate a stored session dict for the last-session sensors."""
    from .protocol import SessionData

    def _dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    return SessionData(
        start_time=_dt(data.get("start_time")),
        duration=data.get("duration", 0),
        on_event_count=data.get("on_event_count"),
        mode=data.get("mode"),
        mode_value=data.get("mode_value"),
        high_pressure_time=data.get("high_pressure_time"),
        low_pressure_time=data.get("low_pressure_time"),
        high_pressure_events=data.get("high_pressure_events"),
        low_pressure_events=data.get("low_pressure_events"),
        average_pressure=data.get("average_pressure"),
        maximum_pressure=data.get("maximum_pressure"),
        last_full_load=_dt(data.get("last_full_load")),
        final_battery_level=data.get("final_battery_level"),
        configured_time=data.get("configured_time"),
        number_of_sectors=data.get("number_of_sectors"),
        session_id=data.get("session_id"),
        user_id=data.get("user_id"),
        tongue_time=data.get("tongue_time"),
        eco_settings=data.get("eco_settings"),
    )
