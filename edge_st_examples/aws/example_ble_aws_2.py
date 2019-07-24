#!/usr/bin/env python

################################################################################
# COPYRIGHT(c) 2018 STMicroelectronics                                         #
#                                                                              #
# Redistribution and use in source and binary forms, with or without           #
# modification, are permitted provided that the following conditions are met:  #
#   1. Redistributions of source code must retain the above copyright notice,  #
#      this list of conditions and the following disclaimer.                   #
#   2. Redistributions in binary form must reproduce the above copyright       #
#      notice, this list of conditions and the following disclaimer in the     #
#      documentation and/or other materials provided with the distribution.    #
#   3. Neither the name of STMicroelectronics nor the names of its             #
#      contributors may be used to endorse or promote products derived from    #
#      this software without specific prior written permission.                #
#                                                                              #
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"  #
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE    #
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE   #
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE    #
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR          #
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF         #
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS     #
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN      #
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)      #
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE   #
# POSSIBILITY OF SUCH DAMAGE.                                                  #
################################################################################

################################################################################
# Author:  Davide Aliprandi, STMicroelectronics                                #
################################################################################


# DESCRIPTION
#
# This application example shows how to connect Bluetooth Low Energy (BLE)
# devices implementing the "BlueST" protocol to a Linux gateway, and to make
# them communicate to the Amazon AWS IoT Cloud through the AWS Greengrass edge
# computing service.
#
# The Greengrass edge computing service allows to perform local computation of
# Lambda functions with the same logic available on the cloud even when the
# connection to the cloud is missing; moreover, as soon as the connection
# becomes available the shadow devices on the cloud get automatically
# synchronized to the local virtual devices.
#
# This application example involves two BLE devices exporting the "Switch"
# feature as specified by the BlueST protocol; pressing the user button on a
# device makes the LED of the other device toggle its status. In particular,
# whenever the user button is pressed on a device, the sending device publishes
# a JSON message on a "sense" topic with its device identifier and the status of
# the button, a simple lambda function swaps the device identifier and publishes
# the new message on an "act" topic, and the recipient device toggles the status
# of its LED.
#
# Moreover, the BLE devices export environmental and inertial features, so that
# data from Pressure, Humidity, Temperature, Accelerometer, Gyroscope, and
# Magnetometer sensors are sent to the IoT Cloud.


# IMPORT

from __future__ import print_function
import sys
import os
import time
import getopt
import json
import logging
from enum import Enum
import threading

from bluepy.btle import BTLEException

from blue_st_sdk.manager import Manager
from blue_st_sdk.manager import ManagerListener
from blue_st_sdk.node import NodeListener
from blue_st_sdk.feature import FeatureListener
from blue_st_sdk.features import *
from blue_st_sdk.utils.blue_st_exceptions import InvalidOperationException

from edge_st_sdk.aws.aws_greengrass import AWSGreengrass
from edge_st_sdk.aws.aws_greengrass import AWSGreengrassListener
from edge_st_sdk.aws.aws_client import AWSClient
from edge_st_sdk.edge_client import EdgeClientListener
from edge_st_sdk.utils.edge_st_exceptions import EdgeSTInvalidOperationException


# PRECONDITIONS
#
# In case you want to modify the SDK, clone the repository and add the location
# of the "EdgeSTSDK_Python" folder to the "PYTHONPATH" environment variable.
#
# On Linux:
#   export PYTHONPATH=/home/<user>/EdgeSTSDK_Python


# CONSTANTS

# Usage message.
USAGE = """Usage:

Use certificate based mutual authentication:
python <application>.py -e <endpoint> -r <root_ca_path>

"""

# Help message.
HELP = """-e, --endpoint
    Your AWS IoT custom endpoint
-r, --rootCA
    Root CA file path
-h, --help
    Help information

"""

# Presentation message.
INTRO = """###############################################
# Edge IoT Example with Amazon Cloud Platform #
###############################################"""

# Bluetooth Low Energy devices' MAC address.
IOT_DEVICE_1_MAC = 'd1:07:fd:84:30:8c'
IOT_DEVICE_2_MAC = 'd7:90:95:be:58:7e'

# Timeouts.
SCANNING_TIME_s = 5
SHADOW_CALLBACK_TIMEOUT_s = 5
SENSORS_DATA_PUBLISHING_TIME_s = 5

# MQTT QoS.
MQTT_QOS_0 = 0
MQTT_QOS_1 = 1

# MQTT Topics.
MQTT_IOT_DEVICE_SWITCH_SENSE_TOPIC = "iot_device/switch_sense"
MQTT_IOT_DEVICE_SWITCH_ACT_TOPIC =   "iot_device/switch_act"
MQTT_IOT_DEVICE_ENV_INE_TOPIC =      "iot_device/env_ine_sense"

# Devices' certificates, private keys, and path on the Linux gateway.
CERTIF_EXT = ".cert.pem"
PRIV_K_EXT = ".private.key"
DEVICES_PATH = "./devices_ble_aws/"
IOT_DEVICE_1_NAME = 'IoT_Device_1'
IOT_DEVICE_2_NAME = 'IoT_Device_2'
IOT_DEVICE_1_CERTIF_PATH = DEVICES_PATH + IOT_DEVICE_1_NAME + CERTIF_EXT
IOT_DEVICE_2_CERTIF_PATH = DEVICES_PATH + IOT_DEVICE_2_NAME + CERTIF_EXT
IOT_DEVICE_1_PRIV_K_PATH = DEVICES_PATH + IOT_DEVICE_1_NAME + PRIV_K_EXT
IOT_DEVICE_2_PRIV_K_PATH = DEVICES_PATH + IOT_DEVICE_2_NAME + PRIV_K_EXT


# SHADOW JSON SCHEMAS

#"IoT_Device_X"
#"state": {
#  "desired": {
#    "welcome": "aws-iot",
#    "switch_status": 0,
#    "pressure": 0,
#    "humidity": 0,
#    "temperature": 0,
#    "accelerometer_x": 0,
#    "accelerometer_y": 0,
#    "accelerometer_z": 0,
#    "gyroscope_x": 0,
#    "gyroscope_y": 0,
#    "gyroscope_z": 0,
#    "magnetometer_x": 0,
#    "magnetometer_y": 0,
#    "magnetometer_z": 0
#  },
#  "reported": {
#    "welcome": "aws-iot"
#  },
#  "delta": {
#    "switch_status": 0,
#    "pressure": 0,
#    "humidity": 0,
#    "temperature": 0,
#    "accelerometer_x": 0,
#    "accelerometer_y": 0,
#    "accelerometer_z": 0,
#    "gyroscope_x": 0,
#    "gyroscope_y": 0,
#    "gyroscope_z": 0,
#    "magnetometer_x": 0,
#    "magnetometer_y": 0,
#    "magnetometer_z": 0
#  }
#}


# CLASSES

# Status of the switch.
class SwitchStatus(Enum):
    OFF = 0
    ON = 1

# Index of the axes.
class AxesIndex(Enum):
    X = 0
    Y = 1
    Z = 2

# Index of the features.
class FeaturesIndex(Enum):
    PRESSURE = 0
    HUMIDITY = 1
    TEMPERATURE = 2
    ACCELEROMETER = 3
    GYROSCOPE = 4
    MAGNETOMETER = 5


# FUNCTIONS

#
# Printing intro.
#
def print_intro():
    print('\n' + INTRO + '\n')

#
# Reading input.
#
def read_input(argv):
    global endpoint, root_ca_path

    # Reading in command-line parameters.
    try:
        opts, args = getopt.getopt(argv, "hwe:k:c:r:", ['help", "endpoint=", "key=","cert=","rootCA='])
        if len(opts) == 0:
            raise getopt.GetoptError("No input parameters!")
        for opt, arg in opts:
            if opt in ("-h", "--help"):
                print(HELP)
                exit(0)
            if opt in ("-e", "--endpoint"):
                endpoint = arg
            if opt in ("-r", "--rootCA"):
                root_ca_path = arg
    except getopt.GetoptError:
        print(USAGE)
        exit(1)

    # Missing configuration parameters.
    missing_configuration = False
    if not endpoint:
        print("Missing '-e' or '--endpoint'")
        missing_configuration = True
    if not root_ca_path:
        print("Missing '-r' or '--rootCA'")
        missing_configuration = True
    if missing_configuration:
        exit(2)

#
# Configure logging.
#
def configure_logging():
    logger = logging.getLogger("Demo")
    logger.setLevel(logging.ERROR)
    streamHandler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    streamHandler.setFormatter(formatter)
    logger.addHandler(streamHandler)


# INTERFACES

#
# Implementation of the interface used by the Manager class to notify that a new
# node has been discovered or that the scanning starts/stops.
#
class MyManagerListener(ManagerListener):

    #
    # This method is called whenever a discovery process starts or stops.
    #
    # @param manager Manager instance that starts/stops the process.
    # @param enabled True if a new discovery starts, False otherwise.
    #
    def on_discovery_change(self, manager, enabled):
        print('Discovery %s.' % ('started' if enabled else 'stopped'))
        if not enabled:
            print()

    #
    # This method is called whenever a new node is discovered.
    #
    # @param manager Manager instance that discovers the node.
    # @param node    New node discovered.
    #
    def on_node_discovered(self, manager, node):
        print('New device discovered: %s.' % (node.get_name()))


#
# Implementation of the interface used by the Node class to notify that a node
# has updated its status.
#
class MyNodeListener(NodeListener):

    #
    # To be called whenever a node changes its status.
    #
    # @param node       Node that has changed its status.
    # @param new_status New node status.
    # @param old_status Old node status.
    #
    def on_status_change(self, node, new_status, old_status):
        print('Device %s from %s to %s.' %
            (node.get_name(), str(old_status), str(new_status)))


#
# Implementation of the interface used by the Feature class to notify that a
# feature has updated its status.
#
class MyFeatureSwitchListener(FeatureListener):

    #
    # Constructor.
    #
    def __init__(self, client, topic):
        super(MyFeatureSwitchListener, self).__init__()
        self._client = client
        self._topic = topic

    #
    # To be called whenever the feature updates its data.
    #
    # @param feature Feature that has updated.
    # @param sample  Data extracted from the feature.
    #
    def on_update(self, feature, sample):
        # Getting value.
        switch_status = feature_switch.FeatureSwitch.get_switch_status(sample)

        # Getting a JSON string representation of the message to publish.
        sample_json_str = json.dumps(
            {'{:s}'.format(
                feature.get_fields_description()[0].get_name()): \
                '({:d}) {:s} {:s}'.format(
                    sample.get_timestamp(),
                    self._client.get_name(),
                    str(switch_status)
                    )})

        # Publishing the message.
        #print('Publishing: %s' % (sample_json_str))
        self._client.publish(self._topic, sample_json_str, MQTT_QOS_0)


#
# Implementation of the interface used by the Feature class to notify that a
# feature has updated its status.
#
class MyFeatureSensorsListener(FeatureListener):

    #
    # Constructor.
    #
    def __init__(self, data):
        super(MyFeatureSensorsListener, self).__init__()
        self._data = data

    #
    # To be called whenever the feature updates its data.
    #
    # @param feature Feature that has updated.
    # @param sample  Data extracted from the feature.
    #
    def on_update(self, feature, sample):
        data = [None] * len(AxesIndex)

        # Getting value.
        if isinstance(feature, feature_pressure.FeaturePressure):
            self._data[FeaturesIndex.PRESSURE.value] = feature_pressure.FeaturePressure.get_pressure(sample)
        elif isinstance(feature, feature_humidity.FeatureHumidity):
            self._data[FeaturesIndex.HUMIDITY.value] = feature_humidity.FeatureHumidity.get_humidity(sample)
        elif isinstance(feature, feature_temperature.FeatureTemperature):
            self._data[FeaturesIndex.TEMPERATURE.value] = feature_temperature.FeatureTemperature.get_temperature(sample)
        elif isinstance(feature, feature_accelerometer.FeatureAccelerometer):
            data[AxesIndex.X.value] = feature_accelerometer.FeatureAccelerometer.get_accelerometer_x(sample)
            data[AxesIndex.Y.value] = feature_accelerometer.FeatureAccelerometer.get_accelerometer_y(sample)
            data[AxesIndex.Z.value] = feature_accelerometer.FeatureAccelerometer.get_accelerometer_z(sample)
            self._data[FeaturesIndex.ACCELEROMETER.value] = data
        elif isinstance(feature, feature_gyroscope.FeatureGyroscope):
            data[AxesIndex.X.value] = feature_gyroscope.FeatureGyroscope.get_gyroscope_x(sample)
            data[AxesIndex.Y.value] = feature_gyroscope.FeatureGyroscope.get_gyroscope_y(sample)
            data[AxesIndex.Z.value] = feature_gyroscope.FeatureGyroscope.get_gyroscope_z(sample)
            self._data[FeaturesIndex.GYROSCOPE.value] = data
        elif isinstance(feature, feature_magnetometer.FeatureMagnetometer):
            data[AxesIndex.X.value] = feature_magnetometer.FeatureMagnetometer.get_magnetometer_x(sample)
            data[AxesIndex.Y.value] = feature_magnetometer.FeatureMagnetometer.get_magnetometer_y(sample)
            data[AxesIndex.Z.value] = feature_magnetometer.FeatureMagnetometer.get_magnetometer_z(sample)
            self._data[FeaturesIndex.MAGNETOMETER.value] = data


#
# Implementation of the interface used by the EdgeClient class to notify that a
# client has updated its status.
#
class MyAWSGreengrassListener(AWSGreengrassListener):

    #
    # To be called whenever the AWS Greengrass service changes its status.
    #
    # @param aws_greengrass AWS Greengrass service that has changed its status.
    # @param new_status     New status.
    # @param old_status     Old status.
    #
    def on_status_change(self, aws_greengrass, new_status, old_status):
        print('AWS Greengrass service with endpoint "%s" from %s to %s.' %
            (aws_greengrass.get_endpoint(), str(old_status), str(new_status)))


#
# Implementation of the interface used by the EdgeClient class to notify that a
# client has updated its status.
#
class MyClientListener(EdgeClientListener):

    #
    # To be called whenever a client changes its status.
    #
    # @param client     Client that has changed its status.
    # @param new_status New status.
    # @param old_status Old status.
    #
    def on_status_change(self, client, new_status, old_status):
        print('Client %s from %s to %s.' %
            (client.get_name(), str(old_status), str(new_status)))


# DEVICES' CALLBACKS

#
# Custom MQTT message callback for first device.
#
def iot_device_1_callback(client, userdata, message):
    global iot_device_1_act_flag, iot_device_1_status

    #print("Receiving: %s" % (message.payload))

    # Getting the client name and the switch status from the message.
    feature_name = feature_switch.FeatureSwitch.FEATURE_DATA_NAME
    if feature_name in message.payload:
        message_json = json.loads(message.payload)
        (ts, client_id, switch_status) = message_json[feature_name].split(" ")

    # Set switch status.
    if client_id == IOT_DEVICE_1_NAME:
        iot_device_1_status = SwitchStatus.ON if switch_status != "0" else SwitchStatus.OFF
        iot_device_1_act_flag = True

#
# Custom MQTT message callback for second device.
#
def iot_device_2_callback(client, userdata, message):
    global iot_device_2_act_flag, iot_device_2_status

    #print("Receiving: %s" % (message.payload))

    # Getting the client name and the switch status from the message.
    feature_name = feature_switch.FeatureSwitch.FEATURE_DATA_NAME
    if feature_name in message.payload:
        message_json = json.loads(message.payload)
        (ts, client_id, switch_status) = message_json[feature_name].split(" ")

    # Set switch status.
    if client_id == IOT_DEVICE_2_NAME:
        iot_device_2_status = SwitchStatus.ON if switch_status != "0" else SwitchStatus.OFF
        iot_device_2_act_flag = True

#
# Handling actuation of devices.
#
def iot_device_act(iot_device, iot_device_feature, iot_device_status, iot_device_client):

    # Writing switch status.
    iot_device.disable_notifications(iot_device_feature)
    iot_device_feature.write_switch_status(iot_device_status.value)
    iot_device.enable_notifications(iot_device_feature)

    # Updating switch shadow device's state.
    state_json_str = '{"state":{"desired":{"switch_status":' + str(iot_device_status.value) + '}}}'
    iot_device_client.update_shadow_state(state_json_str, custom_shadow_callback_update, SHADOW_CALLBACK_TIMEOUT_s)

#
# Sending aggregated sensors data.
#
def iot_device_send_data(iot_device_data, iot_device_client, topic):

    #print('iot_device_send_data()')

    # Getting data.
    pressure = iot_device_data[FeaturesIndex.PRESSURE.value]
    humidity = iot_device_data[FeaturesIndex.HUMIDITY.value]
    temperature = iot_device_data[FeaturesIndex.TEMPERATURE.value]
    accelerometer = iot_device_data[FeaturesIndex.ACCELEROMETER.value]
    gyroscope = iot_device_data[FeaturesIndex.GYROSCOPE.value]
    magnetometer = iot_device_data[FeaturesIndex.MAGNETOMETER.value]

    # Getting a JSON string representation of the message to publish.
    sample_json_str = json.dumps(
        {'Board_id': '{:s}'.format(iot_device_client.get_name()), 
         'Temperature': str(temperature), 
         'Humidity': str(humidity), 
         'Pressure': str(pressure), 
         'ACC-X': str(accelerometer[AxesIndex.X.value]), 
         'ACC-Y': str(accelerometer[AxesIndex.Y.value]), 
         'ACC-Z': str(accelerometer[AxesIndex.Z.value]), 
         'GYR-X': str(gyroscope[AxesIndex.X.value]), 
         'GYR-Y': str(gyroscope[AxesIndex.Y.value]), 
         'GYR-Z': str(gyroscope[AxesIndex.Z.value]), 
         'MAG-X': str(magnetometer[AxesIndex.X.value]), 
         'MAG-Y': str(magnetometer[AxesIndex.Y.value]), 
         'MAG-Z': str(magnetometer[AxesIndex.Z.value])
        })

    # Publishing the message.
    #print('Publishing: %s' % (sample_json_str))
    iot_device_client.publish(topic, sample_json_str, MQTT_QOS_0)

    # Udating shadow state.
    state_json_str = \
        '{"state":{"desired":{"pressure":' + str(pressure) + ', ' + \
        '"humidity":' + str(humidity) + ', ' + \
        '"temperature":' + str(temperature) + ', ' + \
        '"accelerometer_x":' + str(accelerometer[AxesIndex.X.value]) + ', ' + \
        '"accelerometer_y":' + str(accelerometer[AxesIndex.Y.value]) + ', ' + \
        '"accelerometer_z":' + str(accelerometer[AxesIndex.Z.value]) + ', ' + \
        '"gyroscope_x":' + str(gyroscope[AxesIndex.X.value]) + ', ' + \
        '"gyroscope_y":' + str(gyroscope[AxesIndex.Y.value]) + ', ' + \
        '"gyroscope_z":' + str(gyroscope[AxesIndex.Z.value]) + ', ' + \
        '"magnetometer_x":' + str(magnetometer[AxesIndex.X.value]) + ', ' + \
        '"magnetometer_y":' + str(magnetometer[AxesIndex.Y.value]) + ', ' + \
        '"magnetometer_z":' + str(magnetometer[AxesIndex.Z.value]) + '}}}'
    iot_device_client.update_shadow_state(state_json_str, custom_shadow_callback_update, SHADOW_CALLBACK_TIMEOUT_s)


# SHADOW DEVICES' CALLBACKS

#
# Custom shadow callback for "get()" operations.
#
def custom_shadow_callback_get(payload, response_status, token):
    # "payload" is a JSON string ready to be parsed using "json.loads()" both in
    # both Python 2.x and Python 3.x
    print("Get request with token \"" + token + "\" " + response_status)
    #if response_status == "accepted":
    #    state_json_str = json.loads(payload)

#
# Custom shadow callback for "update()" operations.
#
def custom_shadow_callback_update(payload, response_status, token):
    # "payload" is a JSON string ready to be parsed using "json.loads()" both in
    # both Python 2.x and Python 3.x
    print("Update request with token \"" + token + "\" " + response_status)
    #if response_status == "accepted":
    #    state_json_str = json.loads(payload)

#
# Custom shadow callback for "delete()" operations.
#
def custom_shadow_callback_delete(payload, response_status, token):
    # "payload" is a JSON string ready to be parsed using "json.loads()" both in
    # both Python 2.x and Python 3.x
    print("Delete request with token \"" + token + "\" " + response_status)
    #if response_status == "accepted":
    #    state_json_str = json.loads(payload)


# THREADS

#
# Sending aggregated sensors data.
#
class MyFeatureSensorsThread(threading.Thread):

    # Global variables.
    global iot_device_1_data, iot_device_1_client
    global iot_device_2_data, iot_device_2_client

    #
    # Constructor.
    #
    def __init__(self, publishing_time):
        threading.Thread.__init__(self)
        self._publishing_time = publishing_time
        self.daemon = True

    #
    # Run the thread.
    #
    def run(self):
        while True:
            time.sleep(self._publishing_time)
            iot_device_send_data(iot_device_1_data, iot_device_1_client, MQTT_IOT_DEVICE_ENV_INE_TOPIC)
            iot_device_send_data(iot_device_2_data, iot_device_2_client, MQTT_IOT_DEVICE_ENV_INE_TOPIC)


# MAIN APPLICATION

#
# Main application.
#
def main(argv):

    # Global variables.
    global endpoint, root_ca_path
    global iot_device_1_client, iot_device_2_client
    global iot_device_1, iot_device_2
    global iot_device_1_feature_switch, iot_device_2_feature_switch
    global iot_device_1_status, iot_device_2_status
    global iot_device_1_act_flag, iot_device_2_act_flag
    global iot_device_1_data, iot_device_2_data

    # Initial state.
    iot_device_1_status = SwitchStatus.OFF
    iot_device_2_status = SwitchStatus.OFF
    iot_device_1_act_flag = False
    iot_device_2_act_flag = False
    iot_device_1_data = [None] * len(FeaturesIndex)
    iot_device_2_data = [None] * len(FeaturesIndex)

    # Configure logging.
    configure_logging()

    # Printing intro.
    print_intro()

    # Reading input.
    read_input(argv)

    try:
        # Creating Bluetooth Manager.
        manager = Manager.instance()
        manager_listener = MyManagerListener()
        manager.add_listener(manager_listener)

        # Synchronous discovery of Bluetooth devices.
        print('Scanning Bluetooth devices...\n')
        manager.discover(SCANNING_TIME_s)

        # Getting discovered devices.
        discovered_devices = manager.get_nodes()
        if not discovered_devices:
            print('\nNo Bluetooth devices found. Exiting...\n')
            sys.exit(0)

        # Checking discovered devices.
        devices = []
        for discovered in discovered_devices:
            if discovered.get_tag() == IOT_DEVICE_1_MAC:
                iot_device_1 = discovered
                devices.append(iot_device_1)
            elif discovered.get_tag() == IOT_DEVICE_2_MAC:
                iot_device_2 = discovered
                devices.append(iot_device_2)
            if len(devices) == 2:
                break
        if len(devices) < 2:
            print('\nBluetooth setup incomplete. Exiting...\n')
            sys.exit(0)

        # Connecting to the devices.
        for device in devices:
            device.add_listener(MyNodeListener())
            print('Connecting to %s...' % (device.get_name()))
            device.connect()
            print('Connection done.')

        # Getting features.
        print('\nGetting features...')
        iot_device_1_feature_switch = iot_device_1.get_feature(feature_switch.FeatureSwitch)
        iot_device_1_feature_pressure = iot_device_1.get_feature(feature_pressure.FeaturePressure)
        iot_device_1_feature_humidity = iot_device_1.get_feature(feature_humidity.FeatureHumidity)
        iot_device_1_feature_temperature = iot_device_1.get_feature(feature_temperature.FeatureTemperature)
        iot_device_1_feature_accelerometer = iot_device_1.get_feature(feature_accelerometer.FeatureAccelerometer)
        iot_device_1_feature_gyroscope = iot_device_1.get_feature(feature_gyroscope.FeatureGyroscope)
        iot_device_1_feature_magnetometer = iot_device_1.get_feature(feature_magnetometer.FeatureMagnetometer)
        iot_device_2_feature_switch = iot_device_2.get_feature(feature_switch.FeatureSwitch)
        iot_device_2_feature_pressure = iot_device_2.get_feature(feature_pressure.FeaturePressure)
        iot_device_2_feature_humidity = iot_device_2.get_feature(feature_humidity.FeatureHumidity)
        iot_device_2_feature_temperature = iot_device_2.get_feature(feature_temperature.FeatureTemperature)
        iot_device_2_feature_accelerometer = iot_device_2.get_feature(feature_accelerometer.FeatureAccelerometer)
        iot_device_2_feature_gyroscope = iot_device_2.get_feature(feature_gyroscope.FeatureGyroscope)
        iot_device_2_feature_magnetometer = iot_device_2.get_feature(feature_magnetometer.FeatureMagnetometer)

        # Resetting switches.
        print('Resetting switches...')
        iot_device_1_feature_switch.write_switch_status(iot_device_1_status.value)
        iot_device_2_feature_switch.write_switch_status(iot_device_2_status.value)

        # Bluetooth setup complete.
        print('\nBluetooth setup complete.')

        # Initializing Edge Computing.
        print('\nInitializing Edge Computing...\n')
        edge = AWSGreengrass(endpoint, root_ca_path)
        edge.add_listener(MyAWSGreengrassListener())

        # Getting AWS MQTT clients.
        iot_device_1_client = edge.get_client(IOT_DEVICE_1_NAME, IOT_DEVICE_1_CERTIF_PATH, IOT_DEVICE_1_PRIV_K_PATH)
        iot_device_2_client = edge.get_client(IOT_DEVICE_2_NAME, IOT_DEVICE_2_CERTIF_PATH, IOT_DEVICE_2_PRIV_K_PATH)

        # Connecting clients to the cloud.
        iot_device_1_client.add_listener(MyClientListener())
        iot_device_2_client.add_listener(MyClientListener())
        iot_device_1_client.connect()
        iot_device_2_client.connect()

        # Setting subscriptions.
        iot_device_1_client.subscribe(MQTT_IOT_DEVICE_SWITCH_ACT_TOPIC, MQTT_QOS_1, iot_device_1_callback)
        iot_device_2_client.subscribe(MQTT_IOT_DEVICE_SWITCH_ACT_TOPIC, MQTT_QOS_1, iot_device_2_callback)

        # Resetting shadow states.
        state_json_str = '{"state":{"desired":{"switch_status":' + str(iot_device_1_status.value) + '}}}'
        iot_device_1_client.update_shadow_state(state_json_str, custom_shadow_callback_update, SHADOW_CALLBACK_TIMEOUT_s)
        state_json_str = '{"state":{"desired":{"switch_status":' + str(iot_device_2_status.value) + '}}}'
        iot_device_2_client.update_shadow_state(state_json_str, custom_shadow_callback_update, SHADOW_CALLBACK_TIMEOUT_s)

        # Edge Computing Initialized.
        print('\nEdge Computing Initialized.')

        # Handling sensing of devices.
        iot_device_1_feature_switch.add_listener(MyFeatureSwitchListener(iot_device_1_client, MQTT_IOT_DEVICE_SWITCH_SENSE_TOPIC))
        iot_device_1_feature_pressure.add_listener(MyFeatureSensorsListener(iot_device_1_data))
        iot_device_1_feature_humidity.add_listener(MyFeatureSensorsListener(iot_device_1_data))
        iot_device_1_feature_temperature.add_listener(MyFeatureSensorsListener(iot_device_1_data))
        iot_device_1_feature_accelerometer.add_listener(MyFeatureSensorsListener(iot_device_1_data))
        iot_device_1_feature_gyroscope.add_listener(MyFeatureSensorsListener(iot_device_1_data))
        iot_device_1_feature_magnetometer.add_listener(MyFeatureSensorsListener(iot_device_1_data))
        iot_device_2_feature_switch.add_listener(MyFeatureSwitchListener(iot_device_2_client, MQTT_IOT_DEVICE_SWITCH_SENSE_TOPIC))
        iot_device_2_feature_pressure.add_listener(MyFeatureSensorsListener(iot_device_2_data))
        iot_device_2_feature_humidity.add_listener(MyFeatureSensorsListener(iot_device_2_data))
        iot_device_2_feature_temperature.add_listener(MyFeatureSensorsListener(iot_device_2_data))
        iot_device_2_feature_accelerometer.add_listener(MyFeatureSensorsListener(iot_device_2_data))
        iot_device_2_feature_gyroscope.add_listener(MyFeatureSensorsListener(iot_device_2_data))
        iot_device_2_feature_magnetometer.add_listener(MyFeatureSensorsListener(iot_device_2_data))

        # Enabling notifications.
        print('\nEnabling Bluetooth notifications...')
        iot_device_1.enable_notifications(iot_device_1_feature_switch)
        iot_device_1.enable_notifications(iot_device_1_feature_pressure)
        iot_device_1.enable_notifications(iot_device_1_feature_humidity)
        iot_device_1.enable_notifications(iot_device_1_feature_temperature)
        iot_device_1.enable_notifications(iot_device_1_feature_accelerometer)
        iot_device_1.enable_notifications(iot_device_1_feature_gyroscope)
        iot_device_1.enable_notifications(iot_device_1_feature_magnetometer)
        iot_device_2.enable_notifications(iot_device_2_feature_switch)
        iot_device_2.enable_notifications(iot_device_2_feature_pressure)
        iot_device_2.enable_notifications(iot_device_2_feature_humidity)
        iot_device_2.enable_notifications(iot_device_2_feature_temperature)
        iot_device_2.enable_notifications(iot_device_2_feature_accelerometer)
        iot_device_2.enable_notifications(iot_device_2_feature_gyroscope)
        iot_device_2.enable_notifications(iot_device_2_feature_magnetometer)

        # Demo running.
        print('\nDemo running (\"CTRL+C\" to quit)...\n')

        # Starting threads.
        sensors_thread = MyFeatureSensorsThread(SENSORS_DATA_PUBLISHING_TIME_s)
        sensors_thread.start()

        # Infinite loop.
        while True:

            # Getting notifications.
            if iot_device_1.wait_for_notifications(0.05) or iot_device_2.wait_for_notifications(0.05):
                continue

            # Handling actuation of devices.
            if iot_device_1_act_flag:
                iot_device_act(iot_device_1, iot_device_1_feature_switch, iot_device_1_status, iot_device_1_client)
                iot_device_1_act_flag = False
            elif iot_device_2_act_flag:
                iot_device_act(iot_device_2, iot_device_2_feature_switch, iot_device_2_status, iot_device_2_client)
                iot_device_2_act_flag = False

    except (BTLEException, EdgeSTInvalidOperationException) as e:
        print(e)
        print('Exiting...\n')
        sys.exit(0)
    except KeyboardInterrupt:
        try:
            # Exiting.
            print('\nExiting...\n')
            sys.exit(0)
        except SystemExit:
            os._exit(0)


if __name__ == "__main__":

    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
