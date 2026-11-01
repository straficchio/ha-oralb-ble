"""Diagnostics for Oral-B BLE."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

TO_REDACT = {"address", "device_uuid"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "state": {
            "name": data.name,
            "model": data.model,
            "protocol": data.protocol,
            "software_version": data.software_version,
            "state": data.state,
            "state_raw": data.state_raw,
            "battery": data.battery,
            "battery_seconds_left": data.battery_seconds_left,
            "mode": data.mode,
            "brushing_time": data.brushing_time,
            "quadrant": data.quadrant,
            "pressure": data.pressure,
            "smiley": data.smiley,
            "new_sessions": data.new_sessions,
            "rssi": data.rssi,
            "firmware": data.firmware,
            "bootloader": data.bootloader,
            "secondary_firmware": data.secondary_firmware,
            "hardware_version": data.hardware_version,
            "device_uuid": async_redact_data({"device_uuid": data.device_uuid}, TO_REDACT)["device_uuid"],
            "media_content_version": data.media_content_version,
            "hardware_configuration": data.hardware_configuration,
            "memory_map_version": data.memory_map_version,
            "info_sector_version": data.info_sector_version,
            "second_controller_version": data.second_controller_version,
            "sessions_today": data.sessions_today,
            "total_sessions": data.total_sessions,
            "last_sync": data.last_sync.isoformat() if data.last_sync else None,
            "last_session": data.last_session.as_dict() if data.last_session else None,
        },
    }
