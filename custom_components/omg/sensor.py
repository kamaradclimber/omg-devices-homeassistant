"""Support for HeishaMon controlled heatpumps through MQTT."""
from __future__ import annotations
from string import Template
import logging
from dataclasses import dataclass, asdict
from collections.abc import Callable
from typing import Any, Optional
from typing_extensions import Self
import re
import json

from homeassistant.components import mqtt
from homeassistant.components.sensor import (
    SensorEntity,
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorExtraStoredData,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import (
    CONF_NAME,
    CONF_STATE,
    CONF_DEVICE_CLASS,
    CONF_UNIT_OF_MEASUREMENT,
)
from .const import DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify


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
    ]
    _LOGGER.debug(f"Starting bootstrap of sensors with prefix '{discovery_prefix}'")
    router_sensor = OMGRouterSensor(hass, discovery_prefix, config_entry, async_add_entities)
    async_add_entities([router_sensor])

class LoRaDevice:
    @staticmethod
    def match(message: str) -> Optional[str]:
        return None

    def receive(self, message, restore_only) -> None:
        pass

    def __init__(self, message: str):
        # implementations are supposed to use the message to get an id
        pass

    @property
    def id(self) -> str:
        return self._id

    @property
    def full_id(self) -> str:
        return type(self).__name__ + "_" + self.id

class MakerFabsSoilSensorV3JSON(LoRaDevice):
    @staticmethod
    def match(message: str) -> Optional[str]:
        try:
            j = json.loads(message)
            if 'message' not in j:
                return None
            j = json.loads(j['message'])
            if 'node_id' not in j:
                return None
            return j['node_id']
        except json.decoder.JSONDecodeError:
            return None

    def __init__(self, message: str, hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: Callable):
        m = MakerFabsSoilSensorV3JSON.match(message)
        if m is None:
            assert False, "Constructor should not be called if we don't match"
        self._id = m
        self.hass = hass
        self.async_add_entities = async_add_entities
        self.config_entry = config_entry
        self.humidity_sensor = None
        self.temperature_sensor = None
        self.battery_sensor = None
        self.moisture_sensor = None

    def receive(self, message, restore_only):
        # here we assume message is perfectly valid
        j = json.loads(message)
        j = json.loads(j['message'])

        def parse_as_float(sensor: SensorEntity, json: dict, key: str):
            sensor._attr_native_value = float(json[key])

        device_info = {
                "identifiers": {(DOMAIN, self.id)},
                "name": "Lora Temperature/ Humidity/ Soil Moisture Sensor V3",
                "manufacturer": "MakerFabs",
                "hw_version": "V3",
                "suggested_area": "garden",
                "via_device": tuple(self.config_entry.data["via_device"])
                }

        if self.humidity_sensor is None:
            desc = OMGDeviceSensorDescription(
                    key="humidity",
                    name="Humidity",
                    device=self,
                    native_unit_of_measurement="%",
                    device_class=SensorDeviceClass.HUMIDITY,
                    on_receive=parse_as_float
                )
            self.humidity_sensor = OMGDeviceSensor(self.hass, desc, self.config_entry, device_info)
            self.async_add_entities([self.humidity_sensor])

        if self.temperature_sensor is None:
            desc = OMGDeviceSensorDescription(
                    key="temperature",
                    name="Temperature",
                    device=self,
                    native_unit_of_measurement="°C",
                    device_class=SensorDeviceClass.TEMPERATURE,
                    on_receive=parse_as_float
                )
            self.temperature_sensor = OMGDeviceSensor(self.hass, desc, self.config_entry, device_info)
            self.async_add_entities([self.temperature_sensor])

        if self.battery_sensor is None:
            desc = OMGDeviceSensorDescription(
                    key="battery",
                    name="Battery Level",
                    entity_category=EntityCategory.DIAGNOSTIC,
                    suggested_display_precision=2,
                    device=self,
                    native_unit_of_measurement="V",
                    device_class=SensorDeviceClass.VOLTAGE,
                    on_receive=parse_as_float
                )
            self.battery_sensor = OMGDeviceSensor(self.hass, desc, self.config_entry, device_info)
            self.async_add_entities([self.battery_sensor])

        if self.moisture_sensor is None:
            desc = OMGDeviceSensorDescription(
                    key="moisture",
                    name="Moisture",
                    device=self,
                    native_unit_of_measurement="%",
                    suggested_display_precision=0,
                    device_class=SensorDeviceClass.MOISTURE,
                    on_receive=parse_as_float
                )
            self.moisture_sensor = OMGDeviceSensor(self.hass, desc, self.config_entry, device_info)
            self.async_add_entities([self.moisture_sensor])

        if not restore_only:
            self.humidity_sensor.entity_description.on_receive(self.humidity_sensor, j, 'hum')
            self.temperature_sensor.entity_description.on_receive(self.temperature_sensor, j, 'temp')
            self.battery_sensor.entity_description.on_receive(self.battery_sensor, j, 'bat')
            self.moisture_sensor.entity_description.on_receive(self.moisture_sensor, j, 'adc')



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

    def receive(self, message, restore_only):
        # here we assume message is perfectly valid
        j = json.loads(message)
        m = MakerFabsSoilSensorV3.MATCHER.match(j['message'])

        def parse_as_float(sensor: SensorEntity, match: re.Match, group_index: int):
            sensor._attr_native_value = float(match.group(group_index))

        device_info = {
                "identifiers": {(DOMAIN, self.id)},
                "name": "Lora Temperature/ Humidity/ Soil Moisture Sensor V3",
                "manufacturer": "MakerFabs",
                "hw_version": "V3",
                "suggested_area": "garden",
                "via_device": tuple(self.config_entry.data["via_device"])
                }

        if self.humidity_sensor is None:
            desc = OMGDeviceSensorDescription(
                    key="humidity",
                    name="Humidity",
                    device=self,
                    native_unit_of_measurement="%",
                    device_class=SensorDeviceClass.HUMIDITY,
                    on_receive=parse_as_float
                )
            self.humidity_sensor = OMGDeviceSensor(self.hass, desc, self.config_entry, device_info)
            self.async_add_entities([self.humidity_sensor])

        if not restore_only:
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
            self.temperature_sensor = OMGDeviceSensor(self.hass, desc, self.config_entry, device_info)
            self.async_add_entities([self.temperature_sensor])
        if not restore_only:
            self.temperature_sensor.entity_description.on_receive(self.temperature_sensor, m, 4)

        if self.adc_sensor is None:
            desc = OMGDeviceSensorDescription(
                    key="adc",
                    name="ADC",
                    device=self,
                    entity_category=EntityCategory.DIAGNOSTIC,
                    on_receive=parse_as_float
                )
            self.adc_sensor = OMGDeviceSensor(self.hass, desc, self.config_entry, device_info)
            self.async_add_entities([self.adc_sensor])
        if not restore_only:
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
            self.battery_sensor = OMGDeviceSensor(self.hass, desc, self.config_entry, device_info)
            self.async_add_entities([self.battery_sensor])
        if not restore_only:
            self.battery_sensor.entity_description.on_receive(self.battery_sensor, m, 4)

        def parse_moisture(sensor: SensorEntity, match: re.Match, group_index: int):
            battery_level = float(match.group(6)) * 3.3 / 1024
            battery_adjustment_factor = 45
            sensor_value = float(match.group(5)) - (battery_adjustment_factor - 2.0) * battery_level
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
            self.moisture_sensor = OMGDeviceSensor(self.hass, desc, self.config_entry, device_info)
            self.async_add_entities([self.moisture_sensor])
        if not restore_only:
            self.moisture_sensor.entity_description.on_receive(self.moisture_sensor, m, 5)


@dataclass
class OMGRouterExtraStoredData(SensorExtraStoredData):
    # This class will allow to memory devices that sent a message "recently"
    # and restore them at startup of HA
    recent_messages: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        data = super().as_dict()
        data["recent_messages"] = self.recent_messages
        return data

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> Self | None:
        extra  = SensorExtraStoredData.from_dict(restored)
        if extra is None:
            return None
        if "recent_messages" not in restored:
            return None
        return cls(
                extra.native_value,
                extra.native_unit_of_measurement,
                restored['recent_messages']
                )

class OMGRouterSensor(RestoreSensor):
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
        self.recent_messages = dict()

    def route_message(self, message_payload, restore_only=False):
        matching_device = None
        for device in self.known_devices:
            m = type(device).match(message_payload)
            if m is not None and m == device.id:
                matching_device = device
                _LOGGER.debug("We recognized %s-%s", type(matching_device).__name__, matching_device.id)
                break
        if matching_device is None:
            for klass in self.all_devices_classes:
                m = klass.match(message_payload)
                if m is not None:
                    matching_device = klass(message_payload, self.hass, self.config_entry, self._async_add_entities)
                    self.known_devices.append(matching_device)
                    _LOGGER.info("We discovered %s-%s", type(matching_device).__name__, matching_device.id)
                    break
        if matching_device is None:
            _LOGGER.info("Unable to deal with this message for now, submit a PR to support it!")
            return

        self.recent_messages[matching_device.full_id] = message_payload
        matching_device.receive(message_payload, restore_only)

    async def async_added_to_hass(self) -> None:
        """Subscribe to MQTT events"""
        await super().async_added_to_hass()
        if restored_data := await self.async_get_last_sensor_data():
            self._attr_native_value = restored_data.native_value
            self.recent_messages = restored_data.recent_messages
            for device_full_id in self.recent_messages:
                _LOGGER.info(f"Restoring device '{device_full_id}'")
                self.route_message(self.recent_messages[device_full_id], restore_only=True)


        @callback
        def message_received(message):
            """Handle new MQTT messages."""
            self._attr_native_value = message.payload
            self.async_write_ha_state()

            self.route_message(message.payload)


        await mqtt.async_subscribe(
            self.hass, self.mqtt_topic, message_received, 1
        )

    @property
    def extra_restore_state_data(self) -> OMGRouterExtraStoredData:
        return OMGRouterExtraStoredData(
                self.native_value,
                self.native_unit_of_measurement,
                self.recent_messages
        )

    async def async_get_last_sensor_data(self) -> OMGRouterExtraStoredData | None:
        if (restored_last_extra_data := await self.async_get_last_extra_data()) is None:
            return None
        return OMGRouterExtraStoredData.from_dict(restored_last_extra_data.as_dict())

@dataclass
class BaseOMGDeviceDescription:
    device: LoRaDevice
    on_receive: Callable

@dataclass
class OMGDeviceSensorDescription(SensorEntityDescription, BaseOMGDeviceDescription):
    pass

class OMGDeviceSensor(RestoreSensor):
    def __init__(self,
                 hass: HomeAssistant,
                 description: OMGDeviceSensorDescription,
                 config_entry: ConfigEntry,
                 device_info: dict,
                 ) -> None:
        self.hass = hass
        self.entity_description = description
        self._device = description.device
        self.entity_id = f"sensor.{slugify(description.key.replace('/', '_'))}_{slugify(self._device.id)}"
        self.config_entry = config_entry
        self._device_info = device_info
        self._attr_unique_id = (
                f"{config_entry.entry_id}-{self._device.id}-{description.key}"
                )


    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if restored_data := await self.async_get_last_sensor_data():
            self._attr_native_value = restored_data.native_value

    @property
    def device_info(self):
        return self._device_info
