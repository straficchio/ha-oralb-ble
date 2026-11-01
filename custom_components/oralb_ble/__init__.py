"""The Oral-B BLE integration."""

from __future__ import annotations

import logging

from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    async_register_callback,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, MANUFACTURER_ID
from .coordinator import OralBCoordinator
from .models import OralBData

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]

type OralBConfigEntry = ConfigEntry[OralBCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: OralBConfigEntry) -> bool:
    """Set up one brush from a config entry."""
    address: str = entry.data["address"]
    name: str = entry.data.get("name") or address

    initial = OralBData(
        address=address,
        name=name,
        model=entry.data.get("model"),
        protocol=entry.data.get("protocol"),
        software_version=entry.data.get("software_version"),
    )

    coordinator = OralBCoordinator(hass, entry, address, name, initial)
    await coordinator.async_setup()
    coordinator.async_set_updated_data(initial)
    entry.runtime_data = coordinator

    entry.async_on_unload(
        async_register_callback(
            hass,
            coordinator.async_handle_advertisement,
            {"address": address, "manufacturer_id": MANUFACTURER_ID},
            BluetoothScanningMode.PASSIVE,
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # First GATT poll runs in the background: a sleeping brush must not make
    # the config entry fail to set up.
    entry.async_create_background_task(
        hass, coordinator.async_refresh(), f"{DOMAIN} initial poll {address}"
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OralBConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: OralBConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
