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
MQTT_SWITCH_DEVICE_ACT_TOPIC = "switch_device/act"

# Client IDs
SWITCH_DEVICE_1_NAME = "GG_Switch_Device_1"
SWITCH_DEVICE_2_NAME = "GG_Switch_Device_2"

# Events
SWITCH_EVENT = "Status"

# Setup logging to stdout
logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# Creating a greengrass core sdk client
client = greengrasssdk.client('iot-data')

# Retrieving platform information to send from Greengrass Core
my_platform = platform.platform()

# Function handler.
# The 'event' parameter has to be a json object.
# In this case the logic is simple: just a substitution of the client identifier.
# In other more complex scenarios, the new json object to build could be more sophisticated.
def function_handler(event, context):
    if SWITCH_EVENT in event:
        if SWITCH_DEVICE_1_NAME in event[SWITCH_EVENT]:
            new_event = json.dumps({SWITCH_EVENT: event[SWITCH_EVENT].replace(SWITCH_DEVICE_1_NAME, SWITCH_DEVICE_2_NAME)})
        else:
            new_event = json.dumps({SWITCH_EVENT: event[SWITCH_EVENT].replace(SWITCH_DEVICE_2_NAME, SWITCH_DEVICE_1_NAME)})
        client.publish(topic = MQTT_SWITCH_DEVICE_ACT_TOPIC, payload = new_event)
        return
