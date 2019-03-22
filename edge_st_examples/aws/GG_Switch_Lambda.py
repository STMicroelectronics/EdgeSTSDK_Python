#
# Copyright 2010-2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#


import sys
import logging
import json
import greengrasssdk
import platform
import struct
import binascii
import unicodedata


# MQTT
MQTT_IOT_DEVICE_ACT_TOPIC = "iot_device/switch_act"

# Events
SWITCH_EVENT = "Status"

# Client IDs
IOT_DEVICE_1_NAME = 'IoT_Device_1'
IOT_DEVICE_2_NAME = 'IoT_Device_2'

# Setup logging to stdout
logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# Creating a greengrass core sdk client
client = greengrasssdk.client('iot-data')

# Retrieving platform information to send from Greengrass Core
my_platform = platform.platform()

# Function handler.
# The 'event' parameter has to be a json object.
# In this case the logic is simple: just a substitution of the client name.
# In other more complex scenarios, the new json object to build could be more sophisticated.
def lambda_handler(event, context):
    if SWITCH_EVENT in event:
        if IOT_DEVICE_1_NAME in event[SWITCH_EVENT]:
            new_event = json.dumps({SWITCH_EVENT: event[SWITCH_EVENT].replace(IOT_DEVICE_1_NAME, IOT_DEVICE_2_NAME)})
        else:
            new_event = json.dumps({SWITCH_EVENT: event[SWITCH_EVENT].replace(IOT_DEVICE_2_NAME, IOT_DEVICE_1_NAME)})
        client.publish(topic = MQTT_IOT_DEVICE_ACT_TOPIC, payload = new_event)
        return
