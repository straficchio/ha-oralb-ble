"""Sensors for Oral-B BLE."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import OralBCoordinator
from .entity import OralBEntity
from .models import OralBData
from .protocol import MODES_LEGACY, MODES_V006, STATES

PARALLEL_UPDATES = 1

MODE_OPTIONS = sorted(set(MODES_LEGACY.values()) | set(MODES_V006.values()))
STATE_OPTIONS = sorted(set(STATES.values()))
PRESSURE_OPTIONS = [
    "low",
    "normal",
    "high",
    "power button pressed",
    "mode button pressed",
]
QUADRANT_OPTIONS = ["none", "1st", "2nd", "3rd", "4th", "5th", "6th", "last"]
SMILEY_OPTIONS = [
    "off",
    "standard",
    *[f"special {i}" for i in range(2, 12)],
]


def _last_session_attr(name: str) -> Callable[[OralBData], Any]:
    def _get(data: OralBData) -> Any:
        session = data.last_session
        if session is None:
            return None
        return getattr(session, name, None)

    return _get


def _last_session_start(data: OralBData) -> datetime | None:
    return data.last_session.start_time if data.last_session else None


@dataclass(frozen=True, kw_only=True)
class OralBSensorDescription(SensorEntityDescription):
    """Description with a value extractor."""

    value_fn: Callable[[OralBData], Any]
    live: bool = False


SENSORS: tuple[OralBSensorDescription, ...] = (
    OralBSensorDescription(
        key="battery",
        translation_key="battery",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.battery,
    ),
    OralBSensorDescription(
        key="battery_time_remaining",
        translation_key="battery_time_remaining",
        name="Battery time remaining",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: round(data.battery_seconds_left / 60)
        if data.battery_seconds_left is not None
        else None,
    ),
    OralBSensorDescription(
        key="state",
        translation_key="state",
        name="State",
        device_class=SensorDeviceClass.ENUM,
        options=STATE_OPTIONS,
        value_fn=lambda data: data.state if data.state in STATE_OPTIONS else None,
        live=True,
    ),
    OralBSensorDescription(
        key="mode",
        translation_key="mode",
        name="Brushing mode",
        device_class=SensorDeviceClass.ENUM,
        options=MODE_OPTIONS,
        value_fn=lambda data: data.mode if data.mode in MODE_OPTIONS else None,
        live=True,
    ),
    OralBSensorDescription(
        key="pressure",
        translation_key="pressure",
        name="Pressure",
        device_class=SensorDeviceClass.ENUM,
        options=PRESSURE_OPTIONS,
        value_fn=lambda data: data.pressure if data.pressure in PRESSURE_OPTIONS else None,
        live=True,
    ),
    OralBSensorDescription(
        key="brushing_time",
        translation_key="brushing_time",
        name="Brushing time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.brushing_time,
        live=True,
    ),
    OralBSensorDescription(
        key="quadrant",
        translation_key="quadrant",
        name="Quadrant",
        device_class=SensorDeviceClass.ENUM,
        options=QUADRANT_OPTIONS,
        value_fn=lambda data: data.quadrant if data.quadrant in QUADRANT_OPTIONS else None,
        live=True,
    ),
    OralBSensorDescription(
        key="sector",
        translation_key="sector",
        name="Sector",
        icon="mdi:view-grid",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.sector_index,
        live=True,
    ),
    OralBSensorDescription(
        key="sectors",
        translation_key="sectors",
        name="Sectors per session",
        icon="mdi:view-grid-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.total_quadrants,
        live=True,
    ),
    OralBSensorDescription(
        key="last_session_sectors",
        translation_key="last_session_sectors",
        name="Last session sectors",
        icon="mdi:view-grid-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (
            data.last_session.number_of_sectors if data.last_session else None
        ),
    ),
    OralBSensorDescription(
        key="smiley",
        translation_key="smiley",
        name="Smiley",
        device_class=SensorDeviceClass.ENUM,
        options=SMILEY_OPTIONS,
        value_fn=lambda data: data.smiley if data.smiley in SMILEY_OPTIONS else None,
        live=True,
    ),
    OralBSensorDescription(
        key="last_session_duration",
        translation_key="last_session_duration",
        name="Last session duration",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_last_session_attr("duration"),
    ),
    OralBSensorDescription(
        key="last_session_start",
        translation_key="last_session_start",
        name="Last session start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_session_start,
    ),
    OralBSensorDescription(
        key="last_session_mode",
        translation_key="last_session_mode",
        name="Last session mode",
        device_class=SensorDeviceClass.ENUM,
        options=MODE_OPTIONS,
        value_fn=lambda data: (
            data.last_session.mode
            if data.last_session and data.last_session.mode in MODE_OPTIONS
            else None
        ),
    ),
    OralBSensorDescription(
        key="last_session_high_pressure_time",
        translation_key="last_session_high_pressure_time",
        name="Last session high pressure time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda data: (
            data.last_session.high_pressure_time / 10
            if data.last_session and data.last_session.high_pressure_time is not None
            else None
        ),
    ),
    OralBSensorDescription(
        key="last_session_low_pressure_time",
        translation_key="last_session_low_pressure_time",
        name="Last session low pressure time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda data: (
            data.last_session.low_pressure_time / 10
            if data.last_session and data.last_session.low_pressure_time is not None
            else None
        ),
    ),
    OralBSensorDescription(
        key="last_session_average_pressure",
        translation_key="last_session_average_pressure",
        name="Last session average pressure",
        native_unit_of_measurement="mN",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (
            data.last_session.average_pressure * 100
            if data.last_session and data.last_session.average_pressure is not None
            else None
        ),
    ),
    OralBSensorDescription(
        key="last_session_maximum_pressure",
        translation_key="last_session_maximum_pressure",
        name="Last session maximum pressure",
        native_unit_of_measurement="mN",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (
            data.last_session.maximum_pressure * 100
            if data.last_session and data.last_session.maximum_pressure is not None
            else None
        ),
    ),
    OralBSensorDescription(
        key="last_session_high_pressure_events",
        translation_key="last_session_high_pressure_events",
        name="Last session high pressure events",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_last_session_attr("high_pressure_events"),
    ),
    OralBSensorDescription(
        key="last_session_low_pressure_events",
        translation_key="last_session_low_pressure_events",
        name="Last session low pressure events",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_last_session_attr("low_pressure_events"),
    ),
    OralBSensorDescription(
        key="last_session_battery",
        translation_key="last_session_battery",
        name="Last session battery",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_last_session_attr("final_battery_level"),
    ),
    OralBSensorDescription(
        key="sessions_today",
        translation_key="sessions_today",
        name="Sessions today",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.sessions_today,
    ),
    OralBSensorDescription(
        key="total_sessions",
        translation_key="total_sessions",
        name="Total sessions",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.total_sessions,
    ),
    OralBSensorDescription(
        key="model",
        translation_key="model",
        name="Model",
        value_fn=lambda data: data.model,
    ),
    OralBSensorDescription(
        key="protocol",
        translation_key="protocol",
        name="Protocol",
        value_fn=lambda data: f"V{data.protocol:03d}" if data.protocol else None,
    ),
    OralBSensorDescription(
        key="firmware",
        translation_key="firmware",
        name="Firmware",
        value_fn=lambda data: data.firmware,
    ),
    OralBSensorDescription(
        key="bootloader",
        translation_key="bootloader",
        name="Bootloader",
        value_fn=lambda data: data.bootloader,
    ),
    OralBSensorDescription(
        key="secondary_firmware",
        translation_key="secondary_firmware",
        name="Secondary firmware",
        value_fn=lambda data: data.secondary_firmware,
    ),
    OralBSensorDescription(
        key="hardware_version",
        translation_key="hardware_version",
        name="Hardware version",
        value_fn=lambda data: str(data.hardware_version)
        if data.hardware_version is not None
        else None,
    ),
    OralBSensorDescription(
        key="device_uuid",
        translation_key="device_uuid",
        name="Device UUID",
        value_fn=lambda data: data.device_uuid,
    ),
    OralBSensorDescription(
        key="rssi",
        translation_key="rssi",
        name="Signal strength",
        native_unit_of_measurement="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.rssi,
    ),
    OralBSensorDescription(
        key="last_sync",
        translation_key="last_sync",
        name="Last session sync",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.last_sync,
    ),
    OralBSensorDescription(
        key="last_seen",
        translation_key="last_seen",
        name="Last advertisement",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.last_seen,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OralBCoordinator = entry.runtime_data
    live_enabled = entry.options.get("live_sensors", True)
    entities: list[OralBSensor] = []
    for description in SENSORS:
        entity = OralBSensor(coordinator, description)
        if description.live and not live_enabled:
            entity._attr_entity_registry_enabled_default = False
        entities.append(entity)
    async_add_entities(entities)


class OralBSensor(OralBEntity, SensorEntity):
    """A single Oral-B sensor."""

    entity_description: OralBSensorDescription

    def __init__(
        self, coordinator: OralBCoordinator, description: OralBSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        if description.key in {
            "model",
            "protocol",
            "firmware",
            "bootloader",
            "secondary_firmware",
            "hardware_version",
            "device_uuid",
            "rssi",
            "last_sync",
            "last_seen",
        }:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)
