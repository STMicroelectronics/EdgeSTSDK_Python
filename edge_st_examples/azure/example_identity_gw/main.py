# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.

import random
import time
import sys
import os
import json
import requests
import threading
from datetime import datetime, tzinfo, timedelta
import blue_st_sdk
import iothub_client
# pylint: disable=E0611
from iothub_client import IoTHubTransportProvider, IoTHubError

from blue_st_sdk.manager import Manager, ManagerListener
from blue_st_sdk.node import NodeListener
from blue_st_sdk.feature import FeatureListener
from blue_st_sdk.features import *
from blue_st_sdk.firmware_upgrade.firmware_upgrade_nucleo import FirmwareUpgradeNucleo
from blue_st_sdk.firmware_upgrade.firmware_upgrade import FirmwareUpgradeListener
from blue_st_sdk.firmware_upgrade.utils.firmware_file import FirmwareFile
from blue_st_sdk.features.feature_activity_recognition import ActivityType as act
from blue_st_sdk.features.feature_audio_scene_classification import SceneType as scene
from bluepy.btle import BTLEException

from enum import Enum
# from deviceclient.deviceclient import DeviceClient
from edge_st_sdk.azure.azure_client import AzureModuleClient, AzureDeviceClient
from edge_st_sdk.utils.edge_st_exceptions import WrongInstantiationException

# Firmware file paths.
FIRMWARE_PATH = '/app/'
FIRMWARE_EXTENSION = '.bin'
FIRMWARE_FILENAMES = [
    'SENSING1_ASC', \
    'SENSING1_HAR_GMP', \
    'SENSING1_HAR_IGN', \
    'SENSING1_HAR_IGN_WSDM'
]
FIRMWARE_FILE_DICT = {  "SENSING1_ASC" + FIRMWARE_EXTENSION: "audio-classification",
                        "SENSING1_HAR_GMP" + FIRMWARE_EXTENSION: "activity-recognition",
                        "SENSING1_HAR_IGN" + FIRMWARE_EXTENSION: "activity-recognition",
                        "SENSING1_HAR_IGN_WSDM" + FIRMWARE_EXTENSION: "activity-recognition"
                        }
FIRMWARE_DESC_DICT = {  "SENSING1_ASC" + FIRMWARE_EXTENSION: "in-door;out-door;in-vehicle",
                        "SENSING1_HAR_GMP" + FIRMWARE_EXTENSION: "stationary;walking;jogging;biking;driving;stairs",
                        "SENSING1_HAR_IGN" + FIRMWARE_EXTENSION: "stationary;walking;jogging;biking;driving;stairs",
                        "SENSING1_HAR_IGN_WSDM" + FIRMWARE_EXTENSION: "stationary;walking;jogging;biking;driving;stairs"
                        }

BLE1_APPMOD_INPUT   = 'BLE1_App_Input'
BLE1_APPMOD_OUTPUT  = 'BLE1_App_Output'

class simple_utc(tzinfo):
    def tzname(self,**kwargs):
        return "UTC"
    def utcoffset(self, dt):
        return timedelta(0)

# Status of the switch.
class SwitchStatus(Enum):
    OFF = 0
    ON = 1

# Bluetooth Scanning time in seconds.
SCANNING_TIME_s = 5

# Read BLE devices' MAC address from env var with default given
IOT_DEVICE_1_MAC = os.getenv('MAC_ADDR','e3:60:e4:79:91:94')

MODULE_NAME = os.getenv('MODULE_NAME','modaievtapp')
DEVICE_NAME = os.getenv('DEVICE_NAME','bledev0')
DEVICEID = os.environ["IOTEDGE_DEVICEID"]
MODULEID = os.environ["IOTEDGE_MODULEID"]

# String containing Hostname, Device Id & Device Key in the format:
# "HostName=<host_name>;DeviceId=<device_id>;SharedAccessKey=<device_key>"
# The device string cannot have the GatewayHostName={gateway hostname} part since we are not yet connecting as downstream devices
CONNECTION_STRING = os.getenv('CONNECTION_STRING', "HostName=Mridu-IotHub.azure-devices.net;DeviceId=Dev_0;SharedAccessKey=rpdO7rL9wUYHdE8DJFaNhdonH25bsGD6tRPsZZJY6VY=")

# messageTimeout - the maximum time in milliseconds until a message times out.
# The timeout period starts at IoTHubModuleClient.send_event_async.
# By default, messages do not expire.
MESSAGE_TIMEOUT = 10000

# global counters
RECEIVE_CALLBACKS = 0
SEND_CALLBACKS = 0

# Choose HTTP, AMQP or MQTT as transport protocol.  Currently only MQTT is supported.
PROTOCOL = IoTHubTransportProvider.MQTT

# INTERFACES

class MyManagerListener(ManagerListener):

    def on_discovery_change(self, manager, enabled):
        print('Discovery %s.' % ('started' if enabled else 'stopped'))
        if not enabled:
            print()

    def on_node_discovered(self, manager, node):
        print('New device discovered: %s.' % (node.get_name()))


class MyNodeListener(NodeListener):

    def on_status_change(self, node, new_status, old_status):
        print('Device %s went from %s to %s.' %
            (node.get_name(), str(old_status), str(new_status)))


#
# Implementation of the interface used by the FirmwareUpgrade class to notify
# changes when upgrading the firmware.
#
class MyFirmwareUpgradeListener(FirmwareUpgradeListener):

    def __init__(self, azureClient):
        self.module_client = azureClient

    #
    # To be called whenever the firmware has been upgraded correctly.
    #
    # @param debug_console Debug console.
    # @param firmware_file Firmware file.
    #
    def on_upgrade_firmware_complete(self, debug_console, firmware_file):
        global firmware_upgrade_completed
        global firmware_status, firmware_update_file
        print('Firmware upgrade completed. Device is rebooting...')
        # print('Firmware updated to: ' + firmware_file)
        firmware_status = FIRMWARE_FILE_DICT[firmware_update_file]
        print("Firmware status updated to: " + firmware_status)
        print("Firmware description updated to: " + FIRMWARE_DESC_DICT[firmware_update_file])        
        reported_json = {
            "SupportedMethods": {
                "firmwareUpdate--FwPackageUri-string": "Updates device firmware. Use parameter FwPackageUri to specify the URL of the firmware file"
            },
            "AI": {                
                firmware_status: FIRMWARE_DESC_DICT[firmware_update_file]
            },
            "State": {
                "firmware-file": firmware_update_file,
                "fw_update": "not_running",
                "last_fw_update": "success"
            }
        }
        json_string = json.dumps(reported_json)
        self.module_client.update_shadow_state(json_string, send_reported_state_callback, self.module_client)
        print('sent reported properties...with status "success"')
        firmware_upgrade_completed = True

    #
    # To be called whenever there is an error in upgrading the firmware.
    #
    # @param debug_console Debug console.
    # @param firmware_file Firmware file.
    # @param error         Error code.
    #
    def on_upgrade_firmware_error(self, debug_console, firmware_file, error):
        global firmware_upgrade_completed
        global firmware_status, firmware_update_file
        print('Firmware upgrade error: %s.' % (str(error)))
        firmware_status = FIRMWARE_FILE_DICT[firmware_update_file]      
        reported_json = {
            "SupportedMethods": {
                "firmwareUpdate--FwPackageUri-string": "Updates device firmware. Use parameter FwPackageUri to specify the URL of the firmware file"
            },
            "AI": {
                firmware_status: FIRMWARE_DESC_DICT[firmware_update_file]
            },
            "State": {
                "firmware-file": firmware_update_file,
                "fw_update": "not_running",
                "last_fw_update": "failed"
            }
        }
        json_string = json.dumps(reported_json)
        self.module_client.update_shadow_state(json_string, send_reported_state_callback, self.module_client)
        print('sent reported properties...with status "fail"')
        time.sleep(5)
        firmware_upgrade_completed = True

    #
    # To be called whenever there is an update in upgrading the firmware, i.e. a
    # block of data has been correctly sent and it is possible to send a new one.
    #
    # @param debug_console Debug console.
    # @param firmware_file Firmware file.
    # @param bytes_sent    Data sent in bytes.
    # @param bytes_to_send Data to send in bytes.
    #
    def on_upgrade_firmware_progress(self, debug_console, firmware_file, \
        bytes_sent, bytes_to_send):
        print('%d bytes out of %d sent...' % (bytes_sent, bytes_to_send))


# This function will be called every time a method request is received
def firmwareUpdate(method_name, payload, hubManager): 
    global firmware_update_file, update_task
    print('received method call:')
    print('\tmethod name:', method_name)
    print('\tpayload:', payload)
    json_dict = json.loads(payload)
    print ('\nURL to download from:')
    url = json_dict['FwPackageUri']
    print (url)
    filename = url[url.rfind("/")+1:]
    firmware_update_file = filename
    print (filename)

    # Start thread to download and update
    update_task = threading.Thread(target=download_update, args=(url, filename))
    update_task.start()
    print ('\ndownload and update task started')
    return

class MyFeatureListener(FeatureListener):

    num = 0
    
    def __init__(self, deviceClient):
        self.device_client = deviceClient

    def on_update(self, feature, sample):        
        print("feature listener: onUpdate")        
        feature_str = str(feature)
        print(feature_str)
        print(sample)
        aiEventType = 'None'
        aiEvent = 'None'
        if feature.get_name() == "Activity Recognition":
            eventType = feature.get_activity(sample)
            print(eventType)
            if eventType is act.STATIONARY:
                aiEvent = "stationary"
            elif eventType is act.WALKING:
                aiEvent = "walking"
            elif eventType is act.JOGGING:
                aiEvent = "jogging"
            elif eventType is act.BIKING:
                aiEvent = "biking"
            elif eventType is act.DRIVING:
                aiEvent = "driving"
            elif eventType is act.STAIRS:
                aiEvent = "stairs"
            elif eventType is act.NO_ACTIVITY:
                aiEvent = "no_activity"
            aiEventType = "activity-recognition"
        elif feature.get_name() == "Audio Scene Classification":
            eventType = feature.get_scene(sample)
            print(eventType)
            if eventType is scene.INDOOR:
                aiEvent = "in-door"
            elif eventType is scene.OUTDOOR:
                aiEvent = "out-door"
            elif eventType is scene.IN_VEHICLE:
                aiEvent = "in-vehicle"
            elif eventType is scene.UNKNOWN:
                aiEvent = "unknown"
            aiEventType = "audio-classification"
        event_timestamp = feature.get_last_update()
        print("event timestamp: " + event_timestamp.replace(tzinfo=simple_utc()).isoformat().replace('+00:00', 'Z'))

        event_json = {
            "deviceId": DEVICEID,
            "moduleId": MODULEID,
            "aiEventType": aiEventType,
            "aiEvent": aiEvent,
            "ts": event_timestamp.replace(tzinfo=simple_utc()).isoformat().replace('+00:00', 'Z')
        }        
        json_string = json.dumps(event_json)
        print(json_string)

        # msg_txt_formatted = "Device Message Test"
        msg_properties = {}
        self.device_client.publish(json_string, msg_properties, send_confirmation_callback, 0)

        # self.module_client.publish(BLE1_APPMOD_OUTPUT, json_string, send_confirmation_callback, 0)
        self.num += 1

def download_update(url, filename):
    global no_wait

    print('\n>> Download and Update Task')
    print('downloading file...')
    download_file = "/app/" + filename
    r = requests.get(url, stream = True)
    with open(download_file,"wb") as _content: 
        for chunk in r.iter_content(chunk_size=1024):
            if chunk: 
                _content.write(chunk) 
    
    if os.path.isfile(download_file):
        print('download complete')        
    else:
        print('download failure')
        return

    no_wait = True       
    print('\nWaiting to start fw upgrade process....')    
    return

def send_confirmation_callback(message, result, user_context):
    global SEND_CALLBACKS
    print ( "\nConfirmation[%d] received for message with result = %s" % (user_context, result) )
    SEND_CALLBACKS += 1
    print ( "Total calls confirmed: %d" % SEND_CALLBACKS )


def receive_ble1_message_callback(message, context):
    global RECEIVE_CALLBACKS    
    # Getting value.
    message_buffer = message.get_bytearray()
    size = len(message_buffer)
    message_text = message_buffer[:size].decode('utf-8')
    data = message_text.split()[3]
    print('\nble1 receive msg cb << message: \n')


# module_twin_callback is invoked when the module twin's desired properties are updated.
def module_twin_callback(update_state, payload, context):
    global firmware_status
    print ( "\nModule twin callback >> call confirmed\n")
    print('\tpayload:', payload)


def send_reported_state_callback(status_code, context):
    print ( "\nSend reported state callback >> call confirmed\n")
    print ('status code: ', status_code)
    pass


def main(protocol):   

    try:
        print ( "\nPython %s\n" % sys.version )

        # Global variables.
        global iot_device_1
        global iot_device_1_feature_switch
        global iot_device_1_status
        global firmware_upgrade_completed
        global firmware_upgrade_started
        global firmware_status
        global firmware_update_file
        global firmware_desc
        global features, feature_listener, no_wait
        global upgrade_console, upgrade_console_listener
        
        # initialize_client
        module_client = AzureModuleClient(MODULE_NAME, PROTOCOL)

        # Connecting clients to the runtime.
        module_client.connect()
        module_client.set_module_twin_callback(module_twin_callback, module_client)
        module_client.set_module_method_callback(firmwareUpdate, module_client)        
        module_client.subscribe(BLE1_APPMOD_INPUT, receive_ble1_message_callback, module_client)        

        # initialize device client (This can be a downstream device)
        device_client = AzureDeviceClient(DEVICE_NAME, CONNECTION_STRING, PROTOCOL)
        device_client.connect()
        # publish, subscribe in case of a device does not involve a specific topic but goes-to/comes-from IoTHub

        # Initial state.
        firmware_upgrade_completed = False
        firmware_upgrade_started = False
        no_wait = False
        iot_device_1_status = SwitchStatus.OFF

        print ( "Starting the FWModApp module using protocol MQTT...")
        print ( "This module implements a direct method to be invoked from backend or other modules as required")

        # Creating Bluetooth Manager.
        manager = Manager.instance()
        manager_listener = MyManagerListener()
        manager.add_listener(manager_listener)

        while True:
        
            while True:
                # Synchronous discovery of Bluetooth devices.
                print('Scanning Bluetooth devices...\n')
                manager.discover(False, float(SCANNING_TIME_s))

                # Getting discovered devices.
                print('Getting node device...\n')
                discovered_devices = manager.get_nodes()

                # Listing discovered devices.
                if not discovered_devices:
                    print('\nNo Bluetooth devices found.')
                    continue
                else:
                    print('\nAvailable Bluetooth devices:')
                    # Checking discovered devices.
                    devices = []
                    dev_found = False
                    i = 1
                    for discovered in discovered_devices:
                        device_name = discovered.get_name()
                        print('%d) %s: [%s]' % (i, discovered.get_name(), discovered.get_tag()))
                        if discovered.get_tag() == IOT_DEVICE_1_MAC:
                            iot_device_1 = discovered
                            devices.append(iot_device_1)
                            print("IOT_DEVICE device found!")
                            dev_found = True
                            break
                        i += 1
                    if dev_found is True:
                        break

            # Selecting a device.
            # Connecting to the devices.
            for device in devices:
                node_listener = MyNodeListener()
                device.add_listener(node_listener)
                print('Connecting to %s...' % (device.get_name()))
                device.connect()
                print('Connection done.')

            # Getting features.
            print('\nFeatures:')
            i = 1
            features = []
            ai_fw_running = "none"
            firmware_desc = "none"
            for desired_feature in [
                feature_audio_scene_classification.FeatureAudioSceneClassification,
                feature_activity_recognition.FeatureActivityRecognition]:
                feature = iot_device_1.get_feature(desired_feature)
                if feature:
                    features.append(feature)
                    print('%d) %s' % (i, feature.get_name()))
                    if feature.get_name() == "Activity Recognition":
                        ai_fw_running = "activity-recognition"
                        firmware_desc = "stationary;walking;jogging;biking;driving;stairs"
                        print(ai_fw_running + 'FW feature present')
                    elif feature.get_name() == "Audio Scene Classification":
                        ai_fw_running = "audio-classification"
                        firmware_desc = "in-door;out-door;in-vehicle"
                        print(ai_fw_running + ' FW feature present')
            i += 1        
            if not features:
                print('No features found.')
            print('%d) Firmware upgrade' % (i))

            firmware_status = ai_fw_running
            print("firmware reported by module twin: " + firmware_status)
            reported_json = {
                "SupportedMethods": {
                    "firmwareUpdate--FwPackageUri-string": "Updates device firmware. Use parameter FwPackageUri to specify the URL of the firmware file"                
                },
                "AI": {
                    "firmware": firmware_status,
                    firmware_status: firmware_desc
                },
                "State": {
                    "fw_update": "Not_Running"
                }
            }
            json_string = json.dumps(reported_json)
            module_client.update_shadow_state(json_string, send_reported_state_callback, module_client)
            print('sent reported properties...')                

            # Getting notifications about firmware events
            print('\nWaiting for event notifications...\n')        
            feature = features[0]
            # Enabling notifications.
            upgrade_console = FirmwareUpgradeNucleo.get_console(iot_device_1)
            upgrade_console_listener = MyFirmwareUpgradeListener(module_client)
            upgrade_console.add_listener(upgrade_console_listener)

            feature_listener = MyFeatureListener(device_client)
            feature.add_listener(feature_listener)
            iot_device_1.enable_notifications(feature)

            # Demo running.
            print('\nDemo running (\"CTRL+C\" to quit)...\n')        

            try:
                while True:
                    if no_wait:
                        no_wait = False

                        iot_device_1.disable_notifications(feature)
                        feature.remove_listener(feature_listener)
                        upgrade_console.add_listener(upgrade_console_listener)

                        download_file = "/app/" + firmware_update_file
                        print('\nStarting process to upgrade firmware...File: ' + download_file)
                        firmware_upgrade_completed = False
                        firmware_upgrade_started = True

                        firmware = FirmwareFile(download_file)
                        # Now start FW update process using blue-stsdk-python interface
                        print("Starting upgrade now...")
                        upgrade_console.upgrade_firmware(firmware)

                        reported_json = {
                                "SupportedMethods": {
                                    "firmwareUpdate--FwPackageUri-string": "Updates device firmware. Use parameter FwPackageUri to specify the URL of the firmware file"                
                                },
                                "AI": {
                                    firmware_status: firmware_desc
                                },
                                "State": {
                                    "firmware-file": firmware_update_file,
                                    "fw_update": "running"
                                }
                            }
                        json_string = json.dumps(reported_json)
                        module_client.update_shadow_state(json_string, send_reported_state_callback, module_client)
                        print('sent reported properties...with status "running"')

                        while not firmware_upgrade_completed:
                            if iot_device_1.wait_for_notifications(0.05):
                                continue
                        print('firmware upgrade completed...going to re-add feature listener and disconnect from device...')
                        continue

                    if firmware_upgrade_started:
                        if firmware_upgrade_completed:
                            upgrade_console.remove_listener(upgrade_console_listener)
                            feature.add_listener(feature_listener)
                            iot_device_1.enable_notifications(feature)                    
                            firmware_upgrade_completed = False
                            firmware_upgrade_started = False

                            # Disconnecting from the device.                            
                            print('\nApp Disconnecting from %s...' % (iot_device_1.get_name()))
                            iot_device_1.disconnect()
                            print('Disconnection done.\n')
                            iot_device_1.remove_listener(node_listener)
                            print('waiting for device to reboot....')
                            time.sleep(10)
                            print('after sleep...going to try to reconnect with device....')
                            break
                    if iot_device_1.wait_for_notifications(0.05):
                        # time.sleep(2) # workaround for Unexpected Response Issue
                        print("rcvd notification!")
                        continue
            except (OSError, ValueError) as e:
                    print(e)                           

    except BTLEException as e:
        print(e)
        print('Exiting...\n')
        sys.exit(0)        
    except IoTHubError as iothub_error:
        print ( "Unexpected error %s from IoTHub" % iothub_error )
        return
    except KeyboardInterrupt:
        print ( "IoTHubModuleClient sample stopped" )

if __name__ == '__main__':
    main(PROTOCOL)
