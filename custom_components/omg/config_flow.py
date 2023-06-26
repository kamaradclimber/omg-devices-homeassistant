"""Config flow to configure OMG devices integration."""
from __future__ import annotations

from collections.abc import Awaitable
import logging
from typing import Any, Optional
import json

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.config_entry_flow import DiscoveryFlowHandler
from homeassistant.helpers.service_info.mqtt import MqttServiceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def _async_has_devices(_: HomeAssistant) -> bool:
    """MQTT is set as dependency, so that should be sufficient."""
    return True


class HeishaMonFlowHandler(DiscoveryFlowHandler[Awaitable[bool]], domain=DOMAIN):
    """Handle OMG devices config flow. The MQTT step is inherited from the parent class."""

    VERSION = 1

    def __init__(self) -> None:
        """Set up the config flow."""

        self._prefix: Optional[str] = None
        super().__init__(DOMAIN, "omg", _async_has_devices)

    async def async_step_mqtt(self, discovery_info: MqttServiceInfo) -> FlowResult:
        """Handle a flow initialized by MQTT discovery"""
        _LOGGER.debug(
            f"Starting MQTT discovery for OMG devices with {discovery_info.topic}"
        )
        try:
            message = json.loads(discovery_info.payload)
        except json.decoder.JSONDecodeError:
            # not a OMG message, let's ignore it for now
            return self.async_abort(reason="invalid_discovery_info")
        self._prefix = discovery_info.topic.replace("SYStoMQTT", "LORAtoMQTT")
        _LOGGER.debug(f"The integration will use prefix '{self._prefix}'")

        unique_id = f"{DOMAIN}-{self._prefix}"
        existing_ids = self._async_current_ids()
        if unique_id in existing_ids:
            _LOGGER.debug(
                f"[{self._prefix}] ignoring because it has already been configured"
            )
            return self.async_abort(reason="instance_already_configured")

        await self.async_set_unique_id(unique_id)
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm setup to user and create the entry"""

        if not self._prefix:
            return self.async_abort(reason="unsupported_manual_setup")

        data = {"discovery_prefix": self._prefix}

        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                description_placeholders={
                    "discovery_topic": self._prefix,
                },
            )

        return self.async_create_entry(
            title=f"Lora via {self._prefix} topic", data=data
        )
