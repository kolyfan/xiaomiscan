#!/usr/bin/env python
from __future__ import print_function
import binascii
from bluepy import btle
import logging
from logging.handlers import RotatingFileHandler
import requests
import textwrap

# 4c65a8d434fd - living room
# 4c65a8d426c9 - green room
# 4c65a8d69bfd - kitchen
# 4c65a8d57580 - blue room
# 4c65a8d67678 - corridor

def parseRawData(rawData):
# 0 1 2  3 4     5 6     7 8 910    11  121314151617    18  19  20  21222324

#020106 1216    95fe    5020aa01    75  7876d6a8654c    0a  10  01  4b          09094d4a5f48545f563105030f180a180916ffffd333daa7bbf8
#020106 1316    95fe    5020aa01    2c  fd34d4a8654c    04  10  02  fb00        09094d4a5f48545f563105030f180a180916ffffefb8a25e9082
#020106 1516    95fe    5020aa01    46  fd34d4a8654c    0d  10  04  fe00e601    09094d4a5f48545f563105030f180a180916ffffefb8a25e9082


    data = textwrap.wrap(rawData, 2)
    num = 0
    result = {}
    types = {
        '04': 'Temperature',
        '06': 'Humidity',
        '0a': 'Battery',
        '0d': 'TemperatureHumidity'}
    
    if(len(data) >= 23 and data[5] == '95' and data[6] == 'fe' ): # Xiaomi Inc
        data = data[18:25] # get only type, len and value
    else:
        data = []
        return result
    
    # At this moment we will have next data:
    # 0     - type
    # 2     - len
    # 3-6   - value
    
    #  0   1   2   3 4 5 6
    # 04  10  02  fb00
    # 0d  10  04  fe00e601
    
    if(data[0] == '04' and data[2] == '02'): # Temperature
        num = (int(data[4], 16) << 8) + int(data[3], 16)
        result['Temperature'] = int(num / 10) + (num % 10) * 0.1
    elif(data[0] == '06' and data[2] == '02'): # Humidity
        num = (int(data[4], 16) << 8) + int(data[3], 16)
        result['Humidity'] = int(num / 10) + (num % 10) * 0.1
    elif(data[0] == '0a' and data[2] == '01'): # Battery
        result['Battery'] = int(data[3], 16)
    elif(data[0] == '0d' and data[2] == '04'): # TemperatureHumidity
        num = (int(data[4], 16) << 8) + int(data[3], 16)
        result['Temperature'] = int(num / 10) + (num % 10) * 0.1
        num = (int(data[6], 16) << 8) + int(data[5], 16)
        result['Humidity'] = int(num / 10) + (num % 10) * 0.1
        
    return result


logging.basicConfig(filename='/tmp/xiaomiscan.log',format='%(asctime)s %(message)s')
log = logging.getLogger()
handler = RotatingFileHandler('/tmp/xiaomiscan.log',maxBytes=1024*1024,backupCount=0)
log.addHandler(handler)

urlPrefix = "http://192.168.1.18:8080/rest/items/"
indexes = {"4c:65:a8:d4:34:fd":"Living",
           "4c:65:a8:d4:26:c9":"Green",
           "4c:65:a8:d6:9b:fd":"Kitchen",
           "4c:65:a8:d5:75:80":"Blue",
           "4c:65:a8:d6:76:78":"Corridor",
          }

scanner = btle.Scanner()

while True:
    try:
        devices = scanner.scan()
        
        for d in devices:
            if d.getValueText(9) != "MJ_HT_V1":
                continue

            rawData = binascii.b2a_hex(d.rawData).decode('utf-8')
            mac = d.addr
            
            if mac in indexes:
                data = parseRawData(rawData)
                
                if "Humidity" in data:
                    requests.put(urlPrefix + "Humidity" + indexes[mac]+"/state", data=str(data["Humidity"]))
                    # print("Put Humidity [" + str(data["Humidity"]) + "] to mac [" + mac + "]")

                if "Temperature" in data:
                    requests.put(urlPrefix + "Temp" + indexes[mac]+"/state", data=str(data["Temperature"]))
                    # print("Put Temperature [" + str(data["Temperature"]) + "] to mac [" + mac + "]")

                if "Battery" in data:
                    requests.put(urlPrefix + "Battery" + indexes[mac]+"/state", data=str(data["Battery"]))
                    # print("Put Battery [" + str(data["Battery"]) + "] to mac [" + mac + "]")
    except KeyboardInterrupt:
        print('Aborted by user')
        break
    except:
        logging.exception('')
