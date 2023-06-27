# omg-devices-homeassistant

An integration to analyze devices exposed by OpenMQTTGateway and create HA devices accordingly.

## Installation

Installation should be done using [hacs](https://hacs.xyz/).
For now it is a custom repository, follow hacs documentation to know how to install them.

## Configuration

Just make sure you have an MQTT integration configured. Auto-discovery should work.
For now this integration only support a single device type talking via LoRA to OpenMQTTGateway. It should serve as a demonstration and can be extended easily!

## Supported devices

- [Makefabs LoRa Soil Moisture Sensor V3](https://www.makerfabs.com/lora-soil-moisture-sensor-v3.html?search=lora%20soil) with default and [alternate](https://community.home-assistant.io/t/awesome-lora-soil-sensor/304351) firmware.
