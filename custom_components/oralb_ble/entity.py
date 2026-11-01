"""Base entity for Oral-B BLE."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import OralBCoordinator


class OralBEntity(CoordinatorEntity[OralBCoordinator]):
    """Common device info and availability handling."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OralBCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            name=coordinator.data.name or coordinator.address,
            manufacturer=MANUFACTURER,
            model=coordinator.data.model,
            sw_version=coordinator.data.firmware or coordinator.data.software_version,
            hw_version=str(coordinator.data.hardware_version)
            if coordinator.data.hardware_version is not None
            else None,
        )

    @property
    def available(self) -> bool:
        # A sleeping brush is normal.  Keep the last known values available;
        # only the coordinator's own success flag is used for hard failures.
        return True


class OralBDiagnosticEntity(OralBEntity):
    """Diagnostic entity."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
