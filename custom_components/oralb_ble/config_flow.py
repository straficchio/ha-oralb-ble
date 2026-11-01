"""Config flow for Oral-B BLE."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DEFAULT_LIVE_SENSORS,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SESSION_SYNC,
    DOMAIN,
    MANUFACTURER_ID,
    MIN_POLL_INTERVAL_MINUTES,
    SESSION_SLOTS_NEW,
)
from .protocol import parse_advertisement

_LOGGER = logging.getLogger(__name__)

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class OralBConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle discovery and manual setup."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._address: str | None = None
        self._name: str | None = None
        self._model: str | None = None
        self._protocol: int | None = None
        self._software_version: int | None = None

    # ------------------------------------------------------------------
    # Bluetooth discovery
    # ------------------------------------------------------------------

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle a brush discovered by the Bluetooth integration."""
        payload = discovery_info.manufacturer_data.get(MANUFACTURER_ID)
        adv = parse_advertisement(payload) if payload else None
        if adv is None:
            return self.async_abort(reason="not_supported")

        self._discovery = discovery_info
        self._address = discovery_info.address
        self._name = adv.model
        self._model = adv.model
        self._protocol = adv.protocol
        self._software_version = adv.software_version

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {"name": adv.model}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm adding a discovered brush."""
        assert self._address is not None
        if user_input is not None:
            return self._create_entry()

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._name or self._address,
                "address": self._address,
                "model": self._model or "unknown",
                "protocol": f"V{self._protocol:03d}" if self._protocol else "unknown",
            },
        )

    # ------------------------------------------------------------------
    # Manual setup
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user pick a discovered brush or enter a MAC address."""
        discovered: dict[str, str] = {}
        for info in async_discovered_service_info(self.hass, connectable=True):
            payload = info.manufacturer_data.get(MANUFACTURER_ID)
            adv = parse_advertisement(payload) if payload else None
            if adv is None:
                continue
            if self._async_is_configured(info.address):
                continue
            discovered[info.address] = f"{adv.model} ({info.address})"

        if user_input is not None:
            address = user_input.get("address", "").strip()
            if address:
                if not MAC_RE.match(address):
                    return self.async_show_form(
                        step_id="user",
                        data_schema=self._user_schema(discovered),
                        errors={"address": "invalid_mac"},
                    )
                self._address = address.upper()
                self._name = user_input.get("name") or "Oral-B"
                await self.async_set_unique_id(self._address)
                self._abort_if_unique_id_configured()
                return self._create_entry()

            selected = user_input.get("discovered")
            if not selected:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._user_schema(discovered),
                    errors={"base": "no_device_selected"},
                )
            info = next(
                (item for item in async_discovered_service_info(self.hass) if item.address == selected),
                None,
            )
            if info is None:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._user_schema(discovered),
                    errors={"base": "device_not_found"},
                )
            payload = info.manufacturer_data.get(MANUFACTURER_ID)
            adv = parse_advertisement(payload) if payload else None
            self._address = info.address
            self._name = adv.model if adv else (info.name or "Oral-B")
            self._model = adv.model if adv else None
            self._protocol = adv.protocol if adv else None
            self._software_version = adv.software_version if adv else None
            await self.async_set_unique_id(self._address)
            self._abort_if_unique_id_configured()
            return self._create_entry()

        return self.async_show_form(
            step_id="user", data_schema=self._user_schema(discovered)
        )

    def _user_schema(self, discovered: dict[str, str]) -> vol.Schema:
        fields: dict[Any, Any] = {}
        if discovered:
            fields[
                vol.Optional("discovered")
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=address, label=label)
                        for address, label in discovered.items()
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                )
            )
        fields[vol.Optional("address")] = str
        fields[vol.Optional("name")] = str
        return vol.Schema(fields)

    def _async_is_configured(self, address: str) -> bool:
        return any(
            entry.unique_id == address for entry in self._async_current_entries()
        )

    def _create_entry(self) -> FlowResult:
        assert self._address is not None
        return self.async_create_entry(
            title=self._name or self._address,
            data={
                "address": self._address,
                "name": self._name or self._address,
                "model": self._model,
                "protocol": self._protocol,
                "software_version": self._software_version,
            },
        )

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OralBOptionsFlow()


class OralBOptionsFlow(OptionsFlow):
    """Options for polling and session sync."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    "poll_interval",
                    default=options.get(
                        "poll_interval", int(DEFAULT_POLL_INTERVAL.total_seconds() / 60)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_POLL_INTERVAL_MINUTES,
                        max=1440,
                        step=15,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    "session_sync",
                    default=options.get("session_sync", DEFAULT_SESSION_SYNC),
                ): bool,
                vol.Optional(
                    "live_sensors",
                    default=options.get("live_sensors", DEFAULT_LIVE_SENSORS),
                ): bool,
                vol.Optional(
                    "pair_on_connect",
                    default=options.get("pair_on_connect", False),
                ): bool,
                vol.Optional(
                    "session_slots",
                    default=options.get("session_slots", SESSION_SLOTS_NEW),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=250,
                        step=10,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
