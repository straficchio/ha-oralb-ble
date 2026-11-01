"""Buttons for Oral-B BLE."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .ble import OralBConnectionError
from .coordinator import OralBCoordinator
from .entity import OralBEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class OralBButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[OralBCoordinator], Awaitable[None]]


BUTTONS: tuple[OralBButtonDescription, ...] = (
    OralBButtonDescription(
        key="sync_sessions",
        translation_key="sync_sessions",
        name="Sync sessions",
        icon="mdi:sync",
        press_fn=lambda coordinator: coordinator.async_sync_sessions(),
    ),
    OralBButtonDescription(
        key="sync_time",
        translation_key="sync_time",
        name="Sync clock",
        icon="mdi:clock-check",
        press_fn=lambda coordinator: coordinator.async_sync_time(),
    ),
    OralBButtonDescription(
        key="pair",
        translation_key="pair",
        name="Pair / test connection",
        icon="mdi:bluetooth-connect",
        press_fn=lambda coordinator: coordinator.async_pair(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OralBCoordinator = entry.runtime_data
    async_add_entities(
        OralBButton(coordinator, description) for description in BUTTONS
    )


class OralBButton(OralBEntity, ButtonEntity):
    """A command button for a brush."""

    entity_description: OralBButtonDescription

    def __init__(
        self, coordinator: OralBCoordinator, description: OralBButtonDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    async def async_press(self) -> None:
        try:
            await self.entity_description.press_fn(self.coordinator)
        except OralBConnectionError as err:
            raise HomeAssistantError(f"Could not reach the brush: {err}") from err
