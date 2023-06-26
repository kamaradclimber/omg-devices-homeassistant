"""Support for HeishaMon controlled heatpumps through MQTT."""
from __future__ import annotations
from string import Template
import logging
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any, Optional
import re
import json

from homeassistant.components import mqtt
from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
    SensorEntityDescription,
)
from homeassistant.components.template.sensor import SensorTemplate
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers import template as template_helper
from homeassistant.const import (
    CONF_NAME,
    CONF_STATE,
    CONF_DEVICE_CLASS,
    CONF_UNIT_OF_MEASUREMENT,
)
from .const import DOMAIN
from homeassistant.helpers.template_entity import CONF_AVAILABILITY
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify
from homeassistant.components.sensor import (
        SensorEntity,
        SensorDeviceClass,
        SensorEntityDescription,
        )


_LOGGER = logging.getLogger(__name__)

# async_setup_platform should be defined if one wants to support config via configuration.yaml


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from config entry."""
    discovery_prefix = config_entry.data[
        "discovery_prefix"
    ]  # TODO: handle migration of entities
    _LOGGER.debug(f"Starting bootstrap of sensors with prefix '{discovery_prefix}'")
    router_sensor = OMGRouterSensor(hass, discovery_prefix, config_entry, async_add_entities)
    async_add_entities([router_sensor])

class LoRaDevice:
    @staticmethod
    def match(message: str) -> Optional[str]:
        return None

    def receive(self, message, async_add_entities: Callable) -> None:
        pass

    def __init__(self, message: str):
        # implementations are supposed to use the message to get an id
        pass

    @property
    def id(self) -> str:
        return self._id


class MakerFabsSoilSensorV3(LoRaDevice):
    MATCHER = re.compile('ID(\d+) REPLY : SOIL INEDX:(\d+) H:(.+) T:(.+) ADC:(\d+) BAT:(\d+)')

    @staticmethod
    def match(message: str) -> Optional[str]:
        try:
            j = json.loads(message)
            if 'message' not in j:
                return None
            _LOGGER.debug("There is a message key: %s", j['message'])
            m = MakerFabsSoilSensorV3.MATCHER.match(j['message'])
            if m:
                return m.group(1)
            return None
        except json.decoder.JSONDecodeError:
            return None

    def parse(self, message) -> None:
        pass

    def __init__(self, message: str, hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: Callable):
        m = MakerFabsSoilSensorV3.match(message)
        if m is None:
            assert False, "Constructor should not be called if we don't match"
        self._id = m
        self.hass = hass
        self.async_add_entities = async_add_entities
        self.config_entry = config_entry
        self.humidity_sensor = None
        self.temperature_sensor = None
        self.adc_sensor = None
        self.battery_sensor = None
        self.moisture_sensor = None

    def receive(self, message):
        # here we assume message is perfectly valid
        j = json.loads(message)
        m = MakerFabsSoilSensorV3.MATCHER.match(j['message'])

        def parse_as_float(sensor: SensorEntity, match: re.Match, group_index: int):
            sensor._attr_native_value = float(match.group(group_index))

        def parse_as_int(sensor: SensorEntity, match: re.Match, group_index: int):
            sensor._attr_native_value = int(match.group(group_index))

        if self.humidity_sensor is None:
            desc = OMGDeviceSensorDescription(
                    key="humidity",
                    name="Humidity",
                    device=self,
                    native_unit_of_measurement="%",
                    device_class=SensorDeviceClass.HUMIDITY,
                    on_receive=parse_as_float
                )
            self.humidity_sensor = OMGDeviceSensor(self.hass, desc, self.config_entry)
            self.async_add_entities([self.humidity_sensor])
        self.humidity_sensor.entity_description.on_receive(self.humidity_sensor, m, 3)

        if self.temperature_sensor is None:
            desc = OMGDeviceSensorDescription(
                    key="temperature",
                    name="Temperature",
                    device=self,
                    native_unit_of_measurement="°C",
                    device_class=SensorDeviceClass.TEMPERATURE,
                    on_receive=parse_as_float
                )
            self.temperature_sensor = OMGDeviceSensor(self.hass, desc, self.config_entry)
            self.async_add_entities([self.temperature_sensor])
        self.temperature_sensor.entity_description.on_receive(self.temperature_sensor, m, 4)

        if self.adc_sensor is None:
            desc = OMGDeviceSensorDescription(
                    key="adc",
                    name="ADC",
                    device=self,
                    entity_category=EntityCategory.DIAGNOSTIC,
                    on_receive=parse_as_int
                )
            self.adc_sensor = OMGDeviceSensor(self.hass, desc, self.config_entry)
            self.async_add_entities([self.adc_sensor])
        self.adc_sensor.entity_description.on_receive(self.adc_sensor, m, 5)

        def parse_as_battery(sensor: SensorEntity, match: re.Match, group_index: int):
            battery_level = float(match.group(6)) * 3.3 / 1024
            sensor._attr_native_value = battery_level


        if self.battery_sensor is None:
            desc = OMGDeviceSensorDescription(
                    key="battery",
                    name="Battery Level",
                    entity_category=EntityCategory.DIAGNOSTIC,
                    suggested_display_precision=2,
                    device=self,
                    native_unit_of_measurement="V",
                    device_class=SensorDeviceClass.VOLTAGE,
                    on_receive=parse_as_battery
                )
            self.battery_sensor = OMGDeviceSensor(self.hass, desc, self.config_entry)
            self.async_add_entities([self.battery_sensor])
        self.battery_sensor.entity_description.on_receive(self.battery_sensor, m, 4)

        def parse_moisture(sensor: SensorEntity, match: re.Match, group_index: int):
            battery_level = float(match.group(6)) * 3.3 / 1024
            battery_adjustment_factor = 45
            sensor_value = int(match.group(5)) - battery_adjustment_factor * 2.0 * battery_level
            sensor_value = max(sensor_value, 500)
            sensor._attr_native_value = 100 - (( sensor_value - 500)/5)

        if self.moisture_sensor is None:
            desc = OMGDeviceSensorDescription(
                    key="moisture",
                    name="Moisture",
                    device=self,
                    native_unit_of_measurement="%",
                    suggested_display_precision=0,
                    device_class=SensorDeviceClass.MOISTURE,
                    on_receive=parse_moisture
                )
            self.moisture_sensor = OMGDeviceSensor(self.hass, desc, self.config_entry)
            self.async_add_entities([self.moisture_sensor])
        self.moisture_sensor.entity_description.on_receive(self.moisture_sensor, m, 5)




class OMGRouterSensor(SensorEntity):
    """A sensor which will parse incoming message and define new sensor accordingly"""

    def __init__(
        self,
        hass: HomeAssistant,
        mqtt_topic: str,
        config_entry: ConfigEntry,
        async_add_entities: Callable,
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self.config_entry = config_entry
        self.discovery_prefix = config_entry.data[
            "discovery_prefix"
        ]  # TODO: handle migration of entities
        self.mqtt_topic = mqtt_topic

        slug = slugify(mqtt_topic.replace("/", "_"))
        self.entity_id = f"sensor.{slug}"
        self._attr_unique_id = (
            f"{config_entry.entry_id}-{slug}"
        )
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

        self.known_devices = []
        self.all_devices_classes = [MakerFabsSoilSensorV3]
        self._async_add_entities = async_add_entities

    async def async_added_to_hass(self) -> None:
        """Subscribe to MQTT events"""
        await super().async_added_to_hass()

        @callback
        def message_received(message):
            """Handle new MQTT messages."""
            _LOGGER.warn("Received a new mqtt message")
            _LOGGER.warn(message.payload)
            self._attr_native_value = message.payload

            self.async_write_ha_state()


            matching_device = None
            for device in self.known_devices:
                m = type(device).match(message.payload)
                if m is not None and m == device.id:
                    matching_device = device
                    _LOGGER.debug("We recognized %s-%s", type(matching_device).__name__, matching_device.id)
                    break
            if matching_device is None:
                for klass in self.all_devices_classes:
                    m = klass.match(message.payload)
                    if m is not None:
                        matching_device = klass(message.payload, self.hass, self.config_entry, self._async_add_entities)
                        self.known_devices.append(matching_device)
                        _LOGGER.info("We discovered %s-%s", type(matching_device).__name__, matching_device.id)
                        break
            if matching_device is None:
                _LOGGER.info("Unable to deal with this message for now, submit a PR to support it!")
                return

            matching_device.receive(message.payload)



        await mqtt.async_subscribe(
            self.hass, self.mqtt_topic, message_received, 1
        )

@dataclass
class BaseOMGDeviceDescription:
    device: LoRaDevice
    on_receive: Callable

@dataclass
class OMGDeviceSensorDescription(SensorEntityDescription, BaseOMGDeviceDescription):
    pass

class OMGDeviceSensor(SensorEntity):
    def __init__(self,
                 hass: HomeAssistant,
                 description: OMGDeviceSensorDescription,
                 config_entry: ConfigEntry
                 ) -> None:
        self.hass = hass
        self.entity_description = description
        self._device = description.device
        self.entity_id = f"sensor.{slugify(description.key.replace('/', '_'))}_{slugify(self._device.id)}"
        self._attr_unique_id = (
                f"{config_entry.entry_id}-{self._device.id}-{description.key}"
                )

    @property
    def device_info(self):
        return {
                "identifiers": {(DOMAIN, self._device.id)},
                "name": "Lora Temperature/ Humidity/ Soil Moisture Sensor V3",
                "manufacturer": "MakeFabs",
                "via_device": ("unknown")
                }
