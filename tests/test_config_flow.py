"""Home Assistant config flow tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from homeassistant.data_entry_flow import FlowResultType

from custom_components.oralb_ble.const import DOMAIN


def _discovery(address: str = "78:DB:2F:C2:48:BE"):
    info = MagicMock()
    info.address = address
    info.name = "Oral-B iO5"
    # protocol 8, type 0x35 (iO5), sw 42, idle, status 0, 0s, mode 1, quad 0
    info.manufacturer_data = {0x00DC: bytes([8, 0x35, 42, 2, 0, 0, 0, 1, 0, 0, 4])}
    info.rssi = -60
    return info


@pytest.mark.asyncio
async def test_bluetooth_discovery(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "bluetooth"},
        data=_discovery(),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Oral-B iO5"
    assert result["data"]["address"] == "78:DB:2F:C2:48:BE"
    assert result["data"]["protocol"] == 8


@pytest.mark.asyncio
async def test_bluetooth_discovery_duplicate(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "bluetooth"},
        data=_discovery(),
    )
    await hass.config_entries.flow.async_configure(result["flow_id"], {})

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "bluetooth"},
        data=_discovery(),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_manual_flow(hass):
    with patch(
        "custom_components.oralb_ble.config_flow.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"address": "78:DB:2F:C2:48:BE", "name": "My brush"},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "My brush"
    assert result["data"]["address"] == "78:DB:2F:C2:48:BE"


@pytest.mark.asyncio
async def test_manual_flow_select_discovered(hass):
    info = _discovery()
    with patch(
        "custom_components.oralb_ble.config_flow.async_discovered_service_info",
        return_value=[info],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"discovered": "78:DB:2F:C2:48:BE"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Oral-B iO5"
    assert result["data"]["protocol"] == 8


@pytest.mark.asyncio
async def test_manual_flow_invalid_mac(hass):
    with patch(
        "custom_components.oralb_ble.config_flow.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"address": "not-a-mac"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"address": "invalid_mac"}
