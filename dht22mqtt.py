#!/usr/bin/python3

from datetime import datetime
import time
import os
import statistics
import csv
import adafruit_dht
import logging
# import RPi.GPIO as GPIO
from gpiomapping import gpiomapping
import paho.mqtt.client as mqtt

logLevelStr = os.getenv('logLevel', "info")
logLevel = logging.INFO
if logLevelStr == "debug":
    logLevel = logging.DEBUG
if logLevelStr == "warn":
    logLevel = logging.WARN
if logLevelStr == "error":
    logLevel = logging.ERROR

# create logger
logger = logging.getLogger("dht22mqtt")
logger.setLevel(logLevel)

# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logLevel)

# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)

# Begin
dht22mqtt_start_ts = datetime.now()
###############
# MQTT Params
###############
mqtt_topic = os.getenv('topic', 'domoticz/in')
mqtt_idx = os.getenv('idx', None)
mqtt_brokeraddr = os.getenv('broker', '192.168.1.10')
mqtt_username = os.getenv('username', None)
mqtt_password = os.getenv('password', None)

mqtt_lastUptTimestpSec = datetime.now().timestamp()
mqtt_updateDelay = int(os.getenv('updateDelay', '900'))  # 15 minutes
mqtt_updateOnEveryChange = os.getenv('updateOnEveryChange', 'False').lower() in ["true"]

###############
# GPIO params
###############
# TODO check if we can use the GPIO test https://github.com/kgbplus/gpiotest to autodetect pin
# Problems with multiple sensors on the same device
dht22mqtt_refresh = int(os.getenv('poll', '2'))
dht22mqtt_pin = int(os.getenv('pin', '4'))
dht22mqtt_device_type = str(os.getenv('device_type', 'dht22')).lower()
dht22mqtt_temp_unit = os.getenv('unit', 'C')

###############
# MQTT & Logging params
###############
dht22mqtt_mqtt_chatter = str(os.getenv('mqtt_chatter', 'essential')).lower()
dht22mqtt_logging_mode = str(os.getenv('logging', 'None')).lower()
dht22mqtt_sensor_tally = dict()

###############
# Filtering & Sampling Params
###############
dht22mqtt_filtering_enabled = str(os.getenv('filtering', 'enabled')).lower()
dht22_temp_stack = []
dht22_temp_stack_errors = 0
dht22_hum_stack = []
dht22_hum_stack_errors = 0

dht22_stack_size = 10
dht22_std_deviation = 3
dht22_error_count_stack_flush = 3

###############
# Misc
###############

lastTemperature = 0
lastHumidity = 0


###############
# Logging functions
###############
def log2file(filename, params):
    if 'log2file' in dht22mqtt_logging_mode:
        ts_filename = dht22mqtt_start_ts.strftime('%Y-%m-%dT%H-%M-%SZ') + '_' + filename + ".csv"
        with open("/log/" + ts_filename, "a+") as file:
            w = csv.DictWriter(file, delimiter=',', lineterminator='\n', fieldnames=params.keys())
            if file.tell() == 0:
                w.writeheader()
            w.writerow(params)


def log2stdout(msg, type):
    if 'log2stdout' in dht22mqtt_logging_mode:
        if type == 'debug':
            logger.debug(str(msg))
        if type == 'info':
            logger.info(str(msg))
        if type == 'warning':
            logger.warning(str(msg))
        if type == 'error':
            logger.error(str(msg))


###############
# Polling functions
###############
def get_temperature_jitter(temperature):
    return get_temperature(temperature - 0.3), get_temperature(temperature + 0.3)


def get_temperature(temperature):
    if dht22mqtt_temp_unit == 'F':
        temperature = temperature * (9 / 5) + 32
    return temperature


def get_humidity(humidity):
    return humidity


def get_humidity_status(humidity):
    if isinstance(humidity, int):
        if humidity < 30:
            return 2
        elif humidity >= 30 and humidity < 45:
            return 0
        elif humidity >= 45 and humidity < 70:
            return 1
        elif humidity >= 70:
            return 3
    return 0


###############
# Processing function
###############
def process_sensor_value(stack, error, value, value_type):
    # flush stack on accumulation of errors
    if error >= dht22_error_count_stack_flush:
        stack = []
        error = 0

    # init stack
    if len(stack) <= dht22_error_count_stack_flush:
        if value not in stack:
            stack.append(value)
        # use jitter for bootstrap temperature stack
        if value_type == 'temperature':
            low, high = get_temperature_jitter(value)
            stack.append(low)
            stack.append(high)
        return stack, error, None

    # get statistics
    std = statistics.pstdev(stack)
    mean = statistics.mean(stack)

    # compute if outlier or not
    if mean - std * dht22_std_deviation < value < mean + std * dht22_std_deviation:
        outlier = False
        if value not in stack:
            stack.append(value)
        error = 0
    else:
        outlier = True
        error += 1

    # remove last element from stack
    if len(stack) > 10:
        stack.pop(0)
    return stack, error, outlier


###############
# MQTT update functions
###############
def update_essential_mqtt(temperature, humidity, detected):
    global lastTemperature
    global lastHumidity
    global mqtt_lastUptTimestpSec

    if 'essential' in dht22mqtt_mqtt_chatter:
        if detected == 'accurate' or detected == 'bypass':
            # Send to MQTT only if there are differences or if it's been more than `mqtt_updateDelay` min since last update
            change_in_values = mqtt_updateOnEveryChange and temperature != lastTemperature and humidity != lastHumidity
            now_in_seconds = datetime.now().timestamp()
            if change_in_values or (lastTemperature == 0 and lastHumidity == 0) or (now_in_seconds - mqtt_lastUptTimestpSec) >= mqtt_updateDelay:
                payload = '{ "command": "udevice", "idx" : ' + str(mqtt_idx) + ', "nvalue" : 0, "svalue" : "' + str(temperature) + ';' + str(
                    humidity) + ';' + str(get_humidity_status(humidity)) + '", "parse": false }'

                log2stdout(' ### Publishing payload', 'info')
                log2stdout('    ' + payload, 'debug')

                mqtt_lastUptTimestpSec = now_in_seconds
                lastTemperature = temperature
                lastHumidity = humidity
                client.publish(mqtt_topic, payload, qos=1, retain=True)
            else:
                log2stdout('Ignoring MQTT update:', 'debug')
                mqtt_last_update_time_str = datetime.fromtimestamp(mqtt_lastUptTimestpSec).strftime('%Y-%m-%dT%H:%M:%SZ')
                log2stdout('    -> Change in temperature and humidity: ' + str(change_in_values), 'debug')
                log2stdout('    -> Last update was at: ' + mqtt_last_update_time_str, 'debug')

        client.publish(mqtt_topic + "detected", str(detected), qos=1, retain=True)
        client.publish(mqtt_topic + "updated", str(datetime.now()), qos=1, retain=True)


###############
# Setup dht22 sensor
###############
log2stdout('Starting dht22mqtt...', 'info')
log2stdout('Parameters: ', 'info')
log2stdout('  idx = ' + mqtt_idx, 'info')
log2stdout('  brokeraddr = ' + mqtt_brokeraddr, 'info')
log2stdout('  topic = ' + mqtt_topic, 'info')
log2stdout('  updateDelay = ' + str(mqtt_updateDelay), 'info')
log2stdout('  updateOnEveryChange = ' + str(mqtt_updateOnEveryChange), 'info')

if dht22mqtt_device_type == 'dht22' or dht22mqtt_device_type == 'am2302':
    dhtDevice = adafruit_dht.DHT22(gpiomapping[dht22mqtt_pin], use_pulseio=False)
elif dht22mqtt_device_type == 'dht11':
    dhtDevice = adafruit_dht.DHT11(gpiomapping[dht22mqtt_pin], use_pulseio=False)
else:
    log2stdout('Unsupported device ' + dht22mqtt_device_type + '...', 'error')
    log2stdout('Devices supported by this container are DHT11/DHT22/AM2302', 'error')

log2stdout('Setup dht22 sensor: OK', 'info')

###############
# Setup mqtt client
###############
if 'essential' in dht22mqtt_mqtt_chatter:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, mqtt_idx, clean_session=True, userdata=None)

    if mqtt_username:
        client.username_pw_set(username=mqtt_username, password=mqtt_password)

    # set last will for an ungraceful exit
    client.will_set(mqtt_topic + "state", "OFFLINE", qos=1, retain=True)

    # keep alive for 60 times the refresh rate
    client.connect(mqtt_brokeraddr, keepalive=dht22mqtt_refresh * 60)

    client.loop_start()

    client.publish(mqtt_topic + "type", "sensor", qos=1, retain=True)
    client.publish(mqtt_topic + "device", "dht22", qos=1, retain=True)

    client.publish(mqtt_topic + "updated", str(datetime.now()), qos=1, retain=True)

    log2stdout('Setup mqtt client: OK', 'info')

    client.publish(mqtt_topic + "state", "ONLINE", qos=1, retain=True)

log2stdout('Begin capture...', 'info')

while True:
    try:
        dht22_ts = datetime.now().timestamp()
        temperature = get_temperature(dhtDevice.temperature)
        humidity = get_humidity(dhtDevice.humidity)

        temp_data = process_sensor_value(dht22_temp_stack, dht22_temp_stack_errors, temperature, 'temperature')
        dht22_temp_stack = temp_data[0]
        dht22_temp_stack_errors = temp_data[1]
        temperature_outlier = temp_data[2]

        hum_data = process_sensor_value(dht22_hum_stack, dht22_hum_stack_errors, humidity, 'humidity')
        dht22_hum_stack = hum_data[0]
        dht22_hum_stack_errors = hum_data[1]
        humidity_outlier = hum_data[2]

        log2stdout('Last temperature: ' + str(lastTemperature), 'debug')
        log2stdout('Last humidity: ' + str(lastHumidity), 'debug')

        # Since the intuition here is that errors in humidity and temperature readings
        # are heavily correlated, we can skip mqtt if we detect either.
        detected = ''
        if temperature_outlier is False and humidity_outlier is False:
            detected = 'accurate'
        else:
            detected = 'outlier'

        # Check if filtering enabled
        if 'enabled' in dht22mqtt_filtering_enabled:
            update_essential_mqtt(temperature, humidity, detected)
        else:
            update_essential_mqtt(temperature, humidity, 'bypass')

        data = {
            'timestamp': dht22_ts,
            'temperature': temperature,
            'humidity': humidity,
            'temperature_outlier': temperature_outlier,
            'humidity_outlier': humidity_outlier
        }
        log2stdout(data, 'info')
        log2file('recording', data)

        time.sleep(dht22mqtt_refresh)

    except RuntimeError as error:
        # DHT22 throws errors often. Keep reading.
        detected = 'error'
        update_essential_mqtt(None, None, detected)

        data = {'timestamp': dht22_ts, 'error_type': error.args[0]}
        log2stdout(data, 'warning')
        log2file('error', data)

        time.sleep(dht22mqtt_refresh)
        continue

    except Exception as error:
        if 'essential' in dht22mqtt_mqtt_chatter:
            client.disconnect()
        dhtDevice.exit()
        raise error

# Graceful exit
if 'essential' in dht22mqtt_mqtt_chatter:
    client.publish(mqtt_topic + "state", "OFFLINE", qos=2, retain=True)
    client.publish(mqtt_topic + "updated", str(datetime.now()), qos=2, retain=True)
    client.disconnect()
dhtDevice.exit()
