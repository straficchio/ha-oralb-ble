"""Setup/entity tests with mocked Bluetooth."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oralb_ble.const import DOMAIN


@pytest.mark.asyncio
async def test_setup_creates_entities(hass, mock_bluetooth):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Brush",
        unique_id="78:DB:2F:C2:48:BE",
        data={
            "address": "78:DB:2F:C2:48:BE",
            "name": "Test Brush",
            "model": "Oral-B iO5",
            "protocol": 8,
            "software_version": 42,
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.oralb_ble.async_register_callback",
        return_value=lambda: None,
    ), patch(
        "custom_components.oralb_ble.coordinator.OralBCoordinator.async_refresh",
        return_value=None,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    states = {state.entity_id for state in hass.states.async_all()}
    assert "sensor.test_brush_battery" in states
    assert "sensor.test_brush_state" in states
    assert "binary_sensor.test_brush_brushing" in states
    assert "binary_sensor.test_brush_in_range" in states
    assert "button.test_brush_sync_sessions" in states
    assert "button.test_brush_sync_clock" in states
    assert "button.test_brush_pair_test_connection" in states

    coordinator = entry.runtime_data
    info = MagicMock()
    info.address = "78:DB:2F:C2:48:BE"
    info.manufacturer_data = {
        0x00DC: bytes([8, 0x35, 42, 3, 0x82, 1, 30, 1, 0x02, 0, 4])
    }
    info.rssi = -55
    coordinator.async_handle_advertisement(info, None)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_brush_state").state == "running"
    assert hass.states.get("sensor.test_brush_brushing_time").state == "90"
    assert hass.states.get("sensor.test_brush_sector").state == "2"
    assert hass.states.get("sensor.test_brush_sectors_per_session").state == "4"
    assert hass.states.get("binary_sensor.test_brush_brushing").state == "on"
    assert hass.states.get("binary_sensor.test_brush_high_pressure").state == "on"
