"""Binary sensors for Oral-B BLE."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import OralBCoordinator
from .entity import OralBEntity
from .models import OralBData

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class OralBBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[OralBData], bool | None]
    live: bool = False


BINARY_SENSORS: tuple[OralBBinaryDescription, ...] = (
    OralBBinaryDescription(
        key="brushing",
        translation_key="brushing",
        name="Brushing",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda data: data.brushing,
        live=True,
    ),
    OralBBinaryDescription(
        key="charging",
        translation_key="charging",
        name="Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda data: data.charging,
        live=True,
    ),
    OralBBinaryDescription(
        key="new_sessions",
        translation_key="new_sessions",
        name="New sessions available",
        icon="mdi:database-plus",
        value_fn=lambda data: data.new_sessions,
        live=True,
    ),
    OralBBinaryDescription(
        key="in_range",
        translation_key="in_range",
        name="In range",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:bluetooth-connect",
        value_fn=lambda data: bool(
            data.last_seen and dt_util.utcnow() - data.last_seen < timedelta(minutes=10)
        ),
        live=True,
    ),
    OralBBinaryDescription(
        key="high_pressure",
        translation_key="high_pressure",
        name="High pressure",
        icon="mdi:alert-circle",
        value_fn=lambda data: data.pressure == "high",
        live=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OralBCoordinator = entry.runtime_data
    live_enabled = entry.options.get("live_sensors", True)
    entities: list[OralBBinarySensor] = []
    for description in BINARY_SENSORS:
        entity = OralBBinarySensor(coordinator, description)
        if description.live and not live_enabled:
            entity._attr_entity_registry_enabled_default = False
        entities.append(entity)
    async_add_entities(entities)


class OralBBinarySensor(OralBEntity, BinarySensorEntity):
    """A single Oral-B binary sensor."""

    entity_description: OralBBinaryDescription

    def __init__(
        self, coordinator: OralBCoordinator, description: OralBBinaryDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)
