import binascii
import textwrap
import logging
import time
import json
import paho.mqtt.client as mqtt
from bluepy import btle
from logging.handlers import RotatingFileHandler


# 4c65a8d434fd - living room
# 4c65a8d426c9 - green room
# 4c65a8d69bfd - kitchen
# 4c65a8d57580 - blue room
# 4c65a8d67678 - corridor

# You need execute 2 commands on raspbery pi in shell:
# sudo setcap 'cap_net_raw,cap_net_admin+eip' /home/pi/.local/lib/python3.7/site-packages/bluepy/bluepy-helper
# sudo setcap cap_net_raw+ep /usr/bin/hcitool (use which hcitool for determining correct place for hcitool)

indexes = {"4c:65:a8:d4:34:fd": "big_room",
           "4c:65:a8:d4:26:c9": "green_room",
           "4c:65:a8:d6:9b:fd": "kitchen",
           "4c:65:a8:d5:75:80": "blue_room",
           "4c:65:a8:d6:76:78": "corridor",
           }

mqtt_broker = 'raspbian1'


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.connected_flag = True
        log.info('Connected to MQTT broker')
    else:
        client.connected_flag = False
        log.info('Failed to connect to MQTT broker')
    log.info("Connected flags: " + str(flags) + ", result code [" + str(rc) + "]")


def publish_message(topic, message, broker=mqtt_broker):
    broker_address = broker
    log.info("creating new instance")
    client = mqtt.Client("P1")  # create new instance
    client.on_connect = on_connect
    client.connected_flag = None

    log.info("connecting to broker")
    try:
        client.connect(broker_address)  # connect to broker
    except (TimeoutError, ConnectionRefusedError) as exception:
        log.error("Unhandled error appeared: ", str(exception))
        return False

    client.loop_start()
    message_published = False
    counter = 0
    while client.connected_flag is None or counter < 100:
        log.info("Waiting MQTT broker on_connect callback to occur ", counter)
        time.sleep(0.1)
        counter += 1

    if client.connected_flag is None:
        log.error('Failed to get response from MQTT broker in 10 seconds')
    elif client.connected_flag:
        log.info("Publishing message [{message}] to topic [{topic}]", message=message, topic=topic)
        client.publish(topic, message)
        client.disconnect()
        message_published = True
    else:
        log.error("Failed to connect to MQTT broker")

    client.loop_stop()
    return not message_published


def parse_raw_data(raw_data):
    # 0 1 2  3 4     5 6     7 8 9 10    11  121314151617    18  19  20  21222324

    # 020106 1216    95fe    5020aa01    75  7876d6a8654c    0a  10  01  4b
    # 020106 1316    95fe    5020aa01    2c  fd34d4a8654c    04  10  02  fb00
    # 020106 1516    95fe    5020aa01    46  fd34d4a8654c    0d  10  04  fe00e601

    input_data = textwrap.wrap(raw_data, 2)
    result = {}
    types = {
        'Temperature': '04',
        'Humidity': '06',
        'Battery': '0a',
        'TemperatureHumidity': '0d'}

    if len(input_data) >= 23 and input_data[5] == '95' and input_data[6] == 'fe':  # Xiaomi Inc
        work_data = input_data[18:25]  # get only type, len and value
    else:
        return result

    # At this moment we will have next work_data:
    # 0     - type
    # 2     - len
    # 3-6   - value

    # 0   1   2   3 4 5 6
    # 04  10  02  fb00
    # 0d  10  04  fe00e601

    if work_data[0] == types['Temperature'] and work_data[2] == '02':  # Temperature
        num = (int(work_data[4], 16) << 8) + int(work_data[3], 16)
        result['Temperature'] = int(num / 10) + (num % 10) * 0.1
    elif work_data[0] == types['Humidity'] and work_data[2] == '02':  # Humidity
        num = (int(work_data[4], 16) << 8) + int(work_data[3], 16)
        result['Humidity'] = int(num / 10) + (num % 10) * 0.1
    elif work_data[0] == types['Battery'] and work_data[2] == '01':  # Battery
        result['Battery'] = int(work_data[3], 16)
    elif work_data[0] == types['TemperatureHumidity'] and work_data[2] == '04':  # TemperatureHumidity
        num = (int(work_data[4], 16) << 8) + int(work_data[3], 16)
        result['Temperature'] = int(num / 10) + (num % 10) * 0.1
        num = (int(work_data[6], 16) << 8) + int(work_data[5], 16)
        result['Humidity'] = int(num / 10) + (num % 10) * 0.1

    return result


logging.basicConfig(filename='/tmp/xiaomiscan.log', format='%(asctime)s %(message)s')
log = logging.getLogger()
handler = RotatingFileHandler('/tmp/xiaomiscan.log', maxBytes=1024 * 1024, backupCount=0)
log.addHandler(handler)

scanner = btle.Scanner()

while True:
    try:
        # Initialize variables
        start_time = time.time()
        dict_data = {}
        # Structure of dict_data:
        # mac_address: {}
        #   topic: ''
        #   HumidityTotal: float .1
        #   TemperatureTotal: float .1
        #   BatteryTotal: int
        #   Humidity: []
        #   Temperature: []
        #   Battery: []
        #   Message: json
        for element in indexes:
            dict_data[element] = {}
            dict_data[element]['Topic'] = 'xiaomi_temp2mqtt/' + indexes[element]
            dict_data[element]['HumidityTotal'] = -1.0
            dict_data[element]['TemperatureTotal'] = -1.0
            dict_data[element]['BatteryTotal'] = -1.0
            dict_data[element]['Humidity'] = []
            dict_data[element]['Temperature'] = []
            dict_data[element]['Battery'] = []

        while time.time() - start_time < 60:
            devices = scanner.scan()

            for d in devices:
                if d.getValueText(9) != "MJ_HT_V1":
                    continue

                r_data = binascii.b2a_hex(d.rawData).decode('utf-8')
                mac = d.addr

                if mac in dict_data:
                    data = parse_raw_data(r_data)

                    if "Humidity" in data:
                        dict_data[mac]['Humidity'].append(data["Humidity"])

                    if "Temperature" in data:
                        dict_data[mac]['Temperature'].append(data["Temperature"])

                    if "Battery" in data:
                        dict_data[mac]['Battery'].append(data["Battery"])

        for mac in dict_data:
            if len(dict_data[mac]['Humidity']) > 0:
                dict_data[mac]['HumidityTotal'] = \
                    round(float(sum(dict_data[mac]['Humidity']) / len(dict_data[mac]['Humidity'])), 1)
            if len(dict_data[mac]['Temperature']) > 0:
                dict_data[mac]['TemperatureTotal'] = \
                    round(float(sum(dict_data[mac]['Temperature']) / len(dict_data[mac]['Temperature'])), 1)
            if len(dict_data[mac]['Battery']) > 0:
                # No need average battery - it will not change frequently
                dict_data[mac]['BatteryTotal'] = dict_data[mac]['Battery'][0]

            temp_message = {}
            if dict_data[mac]['HumidityTotal'] != -1.0:
                temp_message['Humidity'] = dict_data[mac]['HumidityTotal']
            if dict_data[mac]['TemperatureTotal'] != -1.0:
                temp_message['Temperature'] = dict_data[mac]['TemperatureTotal']
            if dict_data[mac]['BatteryTotal'] != -1.0:
                temp_message['Battery'] = dict_data[mac]['BatteryTotal']
            if len(temp_message) > 0:
                publish_result = publish_message(dict_data[mac]['Topic'], json.dumps(temp_message))

    except KeyboardInterrupt:
        print('Aborted by user')
        break
    except Exception as e:
        log.exception(str(e))
