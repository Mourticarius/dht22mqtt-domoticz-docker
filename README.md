# dht22 temperature/humidity sensor in a docker container

This docker container is based on [dht22mqtt-homeassistant-docker](https://github.com/hvalev/dht22mqtt-homeassistant-docker) ([Docker Hub](https://hub.docker.com/r/hvalev/dht22mqtt-homeassistant)), for more information please check it out.

The main difference is that it sends only essential data directly to a configured MQTT domoticz topic (see: https://www.domoticz.com/wiki/MQTT)

Data sent: temperature + humidity + humidity status

[![build](https://github.com/Mourticarius/dht22mqtt-domoticz-docker/actions/workflows/build.yml/badge.svg)](https://github.com/Mourticarius/dht22mqtt-domoticz-docker/actions/workflows/build.yml)
![Docker Pulls](https://img.shields.io/docker/pulls/mourticarius/dht22mqtt-domoticz)
![Docker Image Size (latest by date)](https://img.shields.io/docker/image-size/mourticarius/dht22mqtt-domoticz)

## How to run it

The following docker run command or docker-compose service will get you up and running with the minimal configuration.
`docker run --device=/dev/gpiomem:/dev/gpiomem -e idx=418 -e broker=192.168.X.X -e pin=4 mourticarius/dht22mqtt-domoticz`

```
version: "3.8"
services:
  dht22mqtt:
    image: mourticarius/dht22mqtt-domoticz
    container_name: dht22mqtt
    devices:
      - /dev/gpiomem:/dev/gpiomem
    environment:
      - idx=418
      - broker=192.168.X.X
      - pin=4
```

## Parameters

The container offers the following configurable environment variables:</br>
| Parameter | Possible values | Description | Default |
| --------- | --------------- | ----------- | ------- |
| `topic` | | MQTT topic to submit to | `domoticz/in` |
| `idx` | | Unique Domoticz identifier for the Temp + Hum device | `None` |
| `broker` | | MQTT broker ip address | `192.168.1.10` |
| `username` | | MQTT username | `None` |
| `password` | | MQTT password | `None` |
| `pin` | | GPIO data pin your sensor is hooked up to | `4` |
| `poll` | | Sampling rate in seconds. Recommended is the range between 2 to 30 seconds. Further information: [_DHT11/DHT22/AM2302 spec sheet_](https://lastminuteengineers.com/dht11-dht22-arduino-tutorial/) | `2` |
| `device_type` | `dht11` or `dht22` | Sensor type. `dht22` also also works for AM2302 | `dht22` |
| `unit` | `C` or `F` | Measurement unit for temperature in Celsius or Fahrenheit | `C` |
| `logging` | `log2stdout\|log2file` | Logging strategy. Possible **_non-mutually exclusive_** values are: `log2stdout` - forwards logs to stdout, inspectable through `docker logs dht22mqtt` and `log2file` which logs temperature and humidity readings to files timestamped at containers' start | `None` |
| `filtering` | `enabled` or `None` | Enables outlier filtering. Disabling this setting will transmit the raw temperature and humidity values to MQTT and(or) the log | `enabled` |
| `mqtt_chatter` | | Enable MQTT communications if set | `essential` |

---

_If you want to run this container to simply record values to files with no MQTT integration, you need to explicitly set `mqtt_chatter` to a blank string. In that case, you can also omit all MQTT related parameters from your docker run or compose configurations._ </br>

## Acknowledgements

All the work has been done in the following resource: </br>
https://github.com/hvalev/dht22mqtt-homeassistant-docker </br>
