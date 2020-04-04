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
import asyncio
import uuid
from six.moves import input
from datetime import datetime, tzinfo, timedelta
import concurrent
import blue_st_sdk


import azure.iot.device.aio
# pylint: disable=E0611
from azure.iot.device.aio import IoTHubModuleClient
from azure.iot.device import Message, MethodResponse

# pylint: disable=E0611

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
from edge_st_sdk.azure.azure_client import AzureModuleClient
from blue_st_sdk.ai_algos.ai_algos import AIAlgos, AIAlgosDebugConsoleListener
from blue_st_sdk.utils.message_listener import MessageListener
from edge_st_sdk.utils.edge_st_exceptions import EdgeSTInvalidOperationException, EdgeSTInvalidDataException

from ble_helper import *

from azure.iot.device import Message, MethodResponse

# Firmware file paths.
FIRMWARE_PATH = '/app/'
FIRMWARE_EXTENSION = '.bin'

BLE1_APPMOD_INPUT   = 'BLE1_App_Input'
BLE1_APPMOD_OUTPUT  = 'BLE1_App_Output'
BLE2_APPMOD_INPUT   = 'BLE2_App_Input'
BLE2_APPMOD_OUTPUT  = 'BLE2_App_Output'

# Global variables.
# Initial state.
iot_device_1 = None
iot_device_2 = None
firmware_upgrade_completed = False
firmware_upgrade_started = False
firmware_update_file = ''
firmware_desc = ''
features1 = []
features2 = [] 
feature_listener1 = None 
feature_listener2 = None
feature_listeners1 = []
feature_listeners2 = []
no_wait = False
upgrade_console = None
upgrade_console_listener = None
fwup_error = False
update_node = None
do_disconnect = False
AIAlgo_msg_completed = False
AIAlgo_msg_process = False
AI_msg = ""
setAIAlgo = False
algo_name = ''
har_algo = ''
start_algo = ''
pub_dev1 = False
pub_dev2 = False
pub_string = ''
do_shadow_update1 = False
shadow_dict1 = {}
do_shadow_update2 = False
shadow_dict2 = {}
do_shadow_update = False
shadow_dict = {}
count = 0
reboot = False
ready = False


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
IOT_DEVICE_1_MAC = os.getenv('MAC_ADDR1','e3:60:e4:79:91:94')
IOT_DEVICE_2_MAC = os.getenv('MAC_ADDR2','ce:61:6b:61:53:c9')

MODULE_NAME = os.getenv('MODULE_NAME','modaievtapp')
DEVICEID = os.environ["IOTEDGE_DEVICEID"]
MODULEID = os.environ["IOTEDGE_MODULEID"]

# global counters
RECEIVE_CALLBACKS = 0
SEND_CALLBACKS = 0

# Choose HTTP, AMQP or MQTT as transport protocol.  Currently only MQTT is supported.
# PROTOCOL = IoTHubTransportProvider.MQTT

# INTERFACES

#
# Implementation of the interface used by the MessageListener class to notify
# message rcv and send completion.
#
class MyMessageListener1(MessageListener):
    
    def on_message_send_complete(self, debug_console, msg, bytes_sent):
        global AIAlgo_msg_process, AIAlgo_msg_completed, AI_msg
        #print("\nmsg listener 1\n")
        if msg == "\r\n" or msg == '\n': # ignore New Line reply
            return
        elif "NNconfidence" in msg: # ignore "NNconfidence = xx%" messages from the node
            return
        else:            
            if AIAlgo_msg_process is True:
                AIAlgo_msg_process = False
                AI_msg = msg
                AIAlgo_msg_completed = True
    
    def on_message_send_error(self, debug_console, msg, error):
        print("msg send error!")

    def on_message_rcv_complete(self, debug_console, msg, bytes_sent):
        print("msg rcv complete!")
    
    def on_message_rcv_error(self, debug_console, msg, error):
        print("msg rcv error!")

#
# Implementation of the interface used by the MessageListener class to notify
# message rcv and send completion.
#
class MyMessageListener2(MessageListener):
    
    def on_message_send_complete(self, debug_console, msg, bytes_sent):
        global AIAlgo_msg_process, AIAlgo_msg_completed, AI_msg
        #print("\nmsg listener 2\n")
        if msg == "\r\n" or msg == '\n': # ignore New Line reply
            return
        elif "NNconfidence" in msg: # ignore "NNconfidence = xx%" messages from the node
            return
        else:            
            if AIAlgo_msg_process is True:
                AIAlgo_msg_process = False
                AI_msg = msg
                AIAlgo_msg_completed = True
    
    def on_message_send_error(self, debug_console, msg, error):
        print("msg send error!")

    def on_message_rcv_complete(self, debug_console, msg, bytes_sent):
        print("msg rcv complete!")
    
    def on_message_rcv_error(self, debug_console, msg, error):
        print("msg rcv error!")

class MyManagerListener(ManagerListener):

    def on_discovery_change(self, manager, enabled):
        print('Discovery %s.' % ('started' if enabled else 'stopped'))
        if not enabled:
            print()

    def on_node_discovered(self, manager, node):
        print('New device discovered: %s.' % (node.get_name()))


class MyNodeListener(NodeListener):

    def __init__(self, azureClient):
        self.module_client = azureClient

    def on_connect(self, node):
        global shadow_dict1, do_shadow_update1, shadow_dict2, do_shadow_update2, do_shadow_update, shadow_dict
        print('Device %s connected.' % (node.get_name()))
                        
        reported_json = {
                "devices": {
                    node.get_name(): {
                        "State": {
                            "ble_conn_status": "connected"
                        }
                }
            }
        }

        #TODO acquire lock to make sure there is no overwrite from other process
        shadow_dict = reported_json
        do_shadow_update = True
        while True:
            if do_shadow_update is False:
                break

        # if node.get_tag() == IOT_DEVICE_1_MAC:
        #     shadow_dict1 = reported_json
        #     do_shadow_update1 = True
        # elif node.get_tag() == IOT_DEVICE_2_MAC:
        #     shadow_dict2 = reported_json
        #     do_shadow_update2 = True       
        
        # self.module_client.update_shadow_state(json_string, send_reported_state_callback, self.module_client)
        # print('sent reported properties...with status "connected"')


    def on_disconnect(self, node, unexpected=False):
        global iot_device_1, iot_device_2
        global do_disconnect, fwup_error, firmware_upgrade_completed, firmware_upgrade_started, update_node, firmware_update_file, no_wait
        global do_shadow_update1, shadow_dict1, do_shadow_update2, shadow_dict2, do_shadow_update, shadow_dict
        print('Device %s disconnected%s.' % \
            (node.get_name(), ' unexpectedly' if unexpected else ''))       

        if unexpected:
            print('\nStart to disconnect from all devices')
            do_disconnect=True
        elif firmware_upgrade_started or no_wait:
            no_wait = False
            firmware_upgrade_started = False            
            firmware_upgrade_completed = True
            reported_json = {
                "devices": {
                    update_node: {
                        "State": {
                            "firmware-file": firmware_update_file,
                            "fw_update": "not_running",
                            "last_fw_update": "failed",
                            "ble_conn_status": "disconnected"
                        }
                    }
                }
            }

            #TODO acquire lock to make sure there is no overwrite from other process
            shadow_dict = reported_json
            do_shadow_update = True
            # No need to wait for async operation to complete?
            while True:
                if do_shadow_update is False:
                    break
            
            # self.module_client.update_shadow_state(json_string, send_reported_state_callback, self.module_client)
            print('sent reported properties for %s...with status "fail"' % update_node)
            fwup_error = True
        else:
            reported_json = {
                "devices": {
                    node.get_name(): {
                        "State": {
                            "ble_conn_status": "disconnected"
                        }
                    }
                }
            }
            #TODO acquire lock to make sure there is no overwrite from other process
            shadow_dict = reported_json
            do_shadow_update = True
            # No need to wait for async operation to complete?
            while True:
                if do_shadow_update is False:
                    break

    def on_status_change(self, node, new_status, old_status):
        print('Device %s went from %s to %s.' %
            (node.get_name(), str(old_status), str(new_status)))


#
# Implementation of the interface used by the FirmwareUpgrade class to notify
# changes when upgrading the firmware.
#
class MyFirmwareUpgradeListener(FirmwareUpgradeListener):

    def __init__(self, azureClient, node):
        self.module_client = azureClient
        self.device = node

    #
    # To be called whenever the firmware has been upgraded correctly.
    #
    # @param debug_console Debug console.
    # @param firmware_file Firmware file.
    #
    def on_upgrade_firmware_complete(self, debug_console, firmware_file, bytes_sent):
        global firmware_upgrade_completed
        global firmware_update_file
        global do_shadow_update1, shadow_dict1, do_shadow_update2, shadow_dict2
        print('Device %s FW Upgrade complete.' % (self.device.get_name()))
        print('%d bytes out of %d sent...' % (bytes_sent, bytes_sent))
        print('Firmware upgrade completed. Device is rebooting...')
        
        reported_json = {
                "devices": {
                    self.device.get_name(): {
                        "State": {
                            "firmware-file": firmware_update_file,
                            "fw_update": "not_running",
                            "last_fw_update": "success"
                        }
                }
            }
        }
        
        #TODO acquire lock to make sure there is no overwrite from other process
        if self.device.get_tag() == IOT_DEVICE_1_MAC:
            shadow_dict1 = reported_json
            do_shadow_update1 = True
        elif self.device.get_tag() == IOT_DEVICE_2_MAC:
            shadow_dict2 = reported_json
            do_shadow_update2 = True
        # self.module_client.update_shadow_state(json_string, send_reported_state_callback, self.module_client)
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
        global firmware_upgrade_completed, fwup_error, do_disconnect
        global firmware_update_file
        global do_shadow_update1, shadow_dict1, do_shadow_update2, shadow_dict2
        print('Firmware upgrade error: %s.' % (str(error)))
        
        reported_json = {
                "devices": {
                    self.device.get_name(): {
                        "State": {
                            "firmware-file": firmware_update_file,
                            "fw_update": "not_running",
                            "last_fw_update": "failed"
                        }
                }
            }
        }

        #TODO acquire lock to make sure there is no overwrite from other process
        if self.device.get_tag() == IOT_DEVICE_1_MAC:
            shadow_dict1 = reported_json
            do_shadow_update1 = True
        elif self.device.get_tag() == IOT_DEVICE_2_MAC:
            shadow_dict2 = reported_json
            do_shadow_update2 = True
        # self.module_client.update_shadow_state(json_string, send_reported_state_callback, self.module_client)
        print('sent reported properties...with status "fail"')
        # time.sleep(5)
        firmware_upgrade_completed = True
        fwup_error = True
        # Exiting.
        # print('\nExiting...module will re-start\n')
        # sys.exit(0)
        print('\nStart to disconnect from all devices')
        do_disconnect=True


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


# This function will be called every time a method request for firmware update is received
def firmwareUpdate(method_name, payload, hubManager):
    global firmware_update_file, update_task, update_node
    print('received method call:')
    print('\tmethod name:', method_name)
    print('\tpayload:', payload)
    json_dict = json.loads(payload)
    print ('\nURL to download from:')
    url = json_dict['FwPackageUri']
    update_node = json_dict['node']
    print (url)
    print ('update_node: ' + str(update_node))
    filename = url[url.rfind("/")+1:]
    firmware_update_file = filename
    print (filename)

    # Start thread to download and update
    update_task = threading.Thread(target=download_update, args=(url, filename))
    update_task.start()
    print ('\ndownload and update task started')
    return

# This function will be called every time a method request for selecting AI Algo is received
def selectAIAlgorithm(method_name, payload, hubManager):
    global setAIAlgo, algo_name, har_algo, start_algo, update_node
    print('received method call:')
    print('method name:', method_name)
    print('payload:', payload)
    json_dict = json.loads(payload)
    print ('AI Algo to set:')
    algo_name = json_dict['Name'] # e.g. asc+har_gmp, asc+har_ign, asc+har_ign_wsdm
    update_node = json_dict['node']
    start_algo = 'har' #MPD: TBD use : json_dict['start_algo']
    # Assumption: Algo name is in format "asc+har_gmp", hence HAR algo is always split('+')[1]
    har_algo = algo_name.split('+')[1].lower()[4:] #e.g. gmp from 'har_gmp'
    print ('algo name: ' + algo_name)
    print ('har algo: ' + har_algo)
    print ('start algo: ' + start_algo)
    setAIAlgo = True
    return


def getAIAlgoDetails(node, console, _timeout = 5):
    global AI_msg, AIAlgo_msg_completed
    if check_ai_feature_in_node(node):
        console.getAIAllAlgoDetails()
        print("Waiting for AI Algo Details from node")
        timeout = time.time() + _timeout
        while True:
            if node.wait_for_notifications(0.05):
                continue
            elif AIAlgo_msg_completed:                    
                print("Algos received:" + AI_msg)
                return AI_msg
            elif time.time() > timeout:
                print("no response for AIAlgos cmd...setting default...")
                return "har_gmp-6976-5058a32f06e267401e79ad81d951e9c5\nhar_ign-1728-03bd25e15ee5dc9b8dbcb8c850dcba01\nhar_ign_wsdm-1728-156fec2c9716d991c6dcbe5ac8b0053f\nasc-5152-637c147537def27e0f4c918395f2d760"
        # return "har_gmp-6976-5058a32f06e267401e79ad81d951e9c5\nhar_ign-1728-03bd25e15ee5dc9b8dbcb8c850dcba01\nhar_ign_wsdm-1728-156fec2c9716d991c6dcbe5ac8b0053f\nasc-5152-637c147537def27e0f4c918395f2d760"
    else:
        print("Node doesn't support AI")
        return ""

class MyFeatureListener(FeatureListener):

    num = 0
    
    def __init__(self, azureClient, node):
        self.module_client = azureClient
        self.device = node

    def on_update(self, feature, sample):
        global pub_dev1, pub_dev2, pub_string
        print("\nfeature listener: onUpdate")
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
            "nodeId": self.device.get_name(),
            "aiEventType": aiEventType,
            "aiEvent": aiEvent,
            "ts": event_timestamp.replace(tzinfo=simple_utc()).isoformat().replace('+00:00', 'Z')
        }
        pub_string = json.dumps(event_json)
        print(pub_string)
        if self.device.get_tag() == IOT_DEVICE_1_MAC:
            pub_dev1 = True
        elif self.device.get_tag() == IOT_DEVICE_2_MAC:
            pub_dev2 = True
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
    #data = message_text.split()[3]
    print('\nble1 receive msg cb << message: \n' + message_text)

def receive_ble2_message_callback(message, context):
    global RECEIVE_CALLBACKS
    # Getting value.
    message_buffer = message.get_bytearray()
    size = len(message_buffer)
    message_text = message_buffer[:size].decode('utf-8')
    #data = message_text.split()[3]
    print('\nble2 receive msg cb << message: \n' + message_text)

# module_twin_callback is invoked when the module twin's desired properties are updated.
def module_twin_callback(update_state, payload, context):
    print ( "\nModule twin callback >> call confirmed\n")
    print('\tpayload:', payload)


def send_reported_state_callback(status_code, context):
    print ( "\nSend reported state callback >> call confirmed\n")
    print ('status code: ', status_code)
    pass


def send_disconnect_status(node, module_client):
    global iot_device_1, iot_device_2, do_shadow_update1, do_shadow_update2, shadow_dict1, shadow_dict2, do_shadow_update, shadow_dict
    reported_json = {
                "devices": {
                    node.get_name(): {
                        "State": {
                            "ble_conn_status": "disconnected"
                        }
                }
            }
        }
    # if node.get_name() == iot_device_1.get_name():
    do_shadow_update = True
    shadow_dict = reported_json
    while True:
        if do_shadow_update is False:
            break
    # elif node.get_name() == iot_device_2.get_name():
    #     do_shadow_update2 = True
    #     shadow_dict2 = reported_json
    #     while True:
    #         if do_shadow_update2 is False:
    #             break
    
    print('sent reported properties for [%s]...with status "disconnected"' % (node.get_name()))


def start_device_fwupdate(fw_console, file, _timeout = 2):
    global fwup_error
    
    download_file = "/app/" +file
    print('\nStarting process to upgrade firmware...File: ' + download_file)   

    firmware = FirmwareFile(download_file)
    # Now start FW update process using blue-stsdk-python interface
    print("Starting upgrade now...")
    fw_console.upgrade_firmware(firmware)                        

    timeout = time.time() + _timeout # wait for 2 seconds to see if there is any fwupdate error
    while True:
        if time.time() > timeout:
            print("no fw update error..going ahead")
            fwup_error = False # redundant
            break
        elif fwup_error:
            print("fw update error")
            break
    if fwup_error:
        return False
    return True


def ble_main_handler_sync(manager, module_client):
    global iot_device_1, iot_device_2, features1, features2, feature_listener1, feature_listener2, feature_listeners1, feature_listeners2
    global upgrade_console, upgrade_console_listener, AIAlgo_msg_completed, AIAlgo_msg_process, AI_msg, reboot, ready
    global do_disconnect, setAIAlgo, no_wait, firmware_desc, firmware_update_file, firmware_upgrade_completed, firmware_upgrade_started
    global update_node, fwup_error, reboot, algo_name, har_algo, start_algo
    global pub_dev1, pub_dev2, pub_string, do_shadow_update1, do_shadow_update2, shadow_dict1, shadow_dict2, do_shadow_update, shadow_dict

    # Forever loop
    while True:

        # Discover till given MAC addresses are found
        while True:
            # Synchronous discovery of Bluetooth devices.
            print('Scanning Bluetooth devices...\n')
            manager.discover(float(SCANNING_TIME_s))

            # Getting discovered devices.
            print('Getting node device...\n')
            discovered_devices = manager.get_nodes()

            # Listing discovered devices.
            if not discovered_devices:
                print('\nNo Bluetooth devices found.')
                time.sleep(2)
                continue
            else:
                print('\nAvailable Bluetooth devices:')
                # Checking discovered devices.
                devices = []
                dev_found = False
                i = 1 # this is just to print the number of the devices discovered
                for discovered in discovered_devices:
                    print('%d) %s: [%s]' % (i, discovered.get_name(), discovered.get_tag()))
                    if discovered.get_tag() == IOT_DEVICE_1_MAC:
                        iot_device_1 = discovered
                        devices.append(iot_device_1)
                        print("IOT_DEVICE 1 device found!")
                    elif discovered.get_tag() == IOT_DEVICE_2_MAC:
                        iot_device_2 = discovered
                        devices.append(iot_device_2)
                        print("IOT_DEVICE 2 device found!")
                    if len(devices) == 2:
                        dev_found = True
                        break
                    i += 1
                if dev_found is True:
                    break

        connected_nodes = ''
        node_listeners = []
        # Selecting a device.
        # Connecting to the devices.
        for device in devices:
            node_listener = MyNodeListener(module_client)
            device.add_listener(node_listener)
            node_listeners.append(node_listener)
            print('Connecting to %s...' % (device.get_name()))
            device.connect()
            print('Connection done.')
            connected_nodes += device.get_name()
            connected_nodes += ';'

        # Getting features.
        print('\nAvailable Features on connected node 1:')
        i = 1
        features1, ai_fw_running1, firmware_desc1 = extract_ai_features_from_node(iot_device_1)            
        print('\nAvailable Features on connected node 2:')
        features2, ai_fw_running2, firmware_desc2 = extract_ai_features_from_node(iot_device_2)
        
        AI_console1 = AIAlgos.get_console(iot_device_1)
        AI_msg_listener1 = MyMessageListener1()
        AI_console1.add_listener(AI_msg_listener1)

        AI_console2 = AIAlgos.get_console(iot_device_2)
        AI_msg_listener2 = MyMessageListener2()
        AI_console2.add_listener(AI_msg_listener2)

        AIAlgo_msg_process = True 
        AI_msg = getAIAlgoDetails(iot_device_1, AI_console1)
        AIAlgo_msg_process = False
        AIAlgo_msg_completed = False
        algos_supported1, AI_AlgoNames1 = extract_algo_details(AI_msg)
        print("\nfirmware reported by node1: " + ai_fw_running1)

        AIAlgo_msg_completed = True
        AIAlgo_msg_process = True 
        AI_msg = getAIAlgoDetails(iot_device_2, AI_console2)
        AIAlgo_msg_process = False
        AIAlgo_msg_completed = False
        algos_supported2, AI_AlgoNames2 = extract_algo_details(AI_msg)
        print("firmware reported by node2: " + ai_fw_running2)

        reported_json = compile_reported_props_from_node(iot_device_1, ai_fw_running1, firmware_desc1, algos_supported1)
        _reported_json = compile_reported_props_from_node(iot_device_2, ai_fw_running2, firmware_desc2, algos_supported2)
        reported_json["devices"].update(_reported_json["devices"])
        do_shadow_update = True
        shadow_dict = reported_json
        while True:
            if do_shadow_update is False:
                print("False set....sent properties..")
                break

        # Getting notifications about firmware events
        print('\nWaiting for event notifications...\n')        

        # Enabling firmware upgrade notifications for device 1.
        upgrade_console1 = FirmwareUpgradeNucleo.get_console(iot_device_1)
        upgrade_console_listener1 = MyFirmwareUpgradeListener(module_client, iot_device_1)
        upgrade_console1.add_listener(upgrade_console_listener1)

        # Enabling firmware upgrade notifications for device 2.
        upgrade_console2 = FirmwareUpgradeNucleo.get_console(iot_device_2)
        upgrade_console_listener2 = MyFirmwareUpgradeListener(module_client, iot_device_2)
        upgrade_console2.add_listener(upgrade_console_listener2)

        for feature in features1:
            feature_listener = MyFeatureListener(module_client, iot_device_1)
            feature.add_listener(feature_listener)
            feature_listeners1.append(feature_listener)
            iot_device_1.enable_notifications(feature)

        for feature in features2:
            feature_listener = MyFeatureListener(module_client, iot_device_2)
            feature.add_listener(feature_listener)
            feature_listeners2.append(feature_listener)
            iot_device_2.enable_notifications(feature)

        # Demo running.
        print("BLE Single Thread running...\n")        

        try:
            while True:
                if do_disconnect:
                    do_disconnect = False
                    time.sleep(1)
                    
                    no_wait = False
                    firmware_upgrade_started = False            
                    firmware_upgrade_completed = True

                    upgrade_console1.remove_listener(upgrade_console_listener1)
                    upgrade_console2.remove_listener(upgrade_console_listener2)

                    for idx, feature in enumerate(features1):
                        feature_listener = feature_listeners1[idx]
                        feature.remove_listener(feature_listener)
                        iot_device_1.disable_notifications(feature)
                    for idx, feature in enumerate(features2):
                        feature_listener = feature_listeners2[idx]
                        feature.remove_listener(feature_listener)
                        iot_device_2.disable_notifications(feature)

                    # Disconnecting from the device.                            
                    for idx, device in enumerate(devices):
                        print('\nApp Disconnecting from %s...' % (device.get_name()))                           
                        device.remove_listener(node_listeners[idx])
                        device.disconnect()
                        send_disconnect_status(device, module_client)

                    print('Disconnection done.\n')                                            
                    print('waiting to reconnect....')
                    time.sleep(2)
                    print('after 2 sec sleep...going to try to reconnect with device....')
                    break
                if setAIAlgo:
                    setAIAlgo = False
                    print('update node:' + update_node)
                    if update_node and update_node == iot_device_1.get_name():
                        if check_ai_feature_in_node(iot_device_1):                                
                            AI_console1.setAIAlgo(AI_AlgoNames1[algo_name], har_algo, start_algo)
                        else:
                            print("Device does not support AI")                            
                    elif update_node and update_node == iot_device_2.get_name():
                        if check_ai_feature_in_node(iot_device_1):                                
                            AI_console2.setAIAlgo(AI_AlgoNames2[algo_name], har_algo, start_algo)
                        else:
                            print("Device does not support AI")                            
                    continue
                if no_wait:
                    no_wait = False
                    print('update node:' + update_node)
                    if update_node and update_node == iot_device_1.get_name():
                        prepare_listeners_for_fwupdate(iot_device_1, features1, feature_listeners1, AI_console1, 
                                                    upgrade_console_listener1, upgrade_console1)
                    elif update_node and update_node == iot_device_2.get_name():
                        prepare_listeners_for_fwupdate(iot_device_2, features2, feature_listeners2, AI_console2, 
                                                    upgrade_console_listener2, upgrade_console2)
                    else:
                        print("invalid device request")
                        firmware_upgrade_completed = True
                        firmware_upgrade_started = False
                        #TODO send reported properties as error and set         
                        continue

                    firmware_upgrade_completed = False
                    firmware_upgrade_started = True

                    if update_node and update_node == iot_device_1.get_name():
                        if not start_device_fwupdate(upgrade_console1, firmware_update_file):
                            firmware_upgrade_completed = True
                            firmware_upgrade_started = False
                            continue
                    elif update_node and update_node == iot_device_2.get_name():
                        if not start_device_fwupdate(upgrade_console2, firmware_update_file):
                            firmware_upgrade_completed = True
                            firmware_upgrade_started = False
                            continue

                    reported_json = {
                            "devices": {
                                update_node: {
                                    "State": {
                                        "firmware-file": firmware_update_file,
                                        "fw_update": "running"
                                    }
                            }
                        }
                    }

                    do_shadow_update = True
                    shadow_dict = reported_json
                    while True:
                        if do_shadow_update is False:
                            break
                    print('sent reported properties...with status "running"')

                    while not firmware_upgrade_completed:
                        if fwup_error:
                            break
                        if iot_device_1.wait_for_notifications(0.05) or iot_device_2.wait_for_notifications(0.05):
                            continue
                    print('firmware upgrade completed...going to disconnect from device...')
                    continue

                if firmware_upgrade_started:
                    if firmware_upgrade_completed:
                        upgrade_console1.remove_listener(upgrade_console_listener1)
                        upgrade_console2.remove_listener(upgrade_console_listener2)

                        for idx, feature in enumerate(features1):
                            feature_listener = feature_listeners1[idx]
                            feature.remove_listener(feature_listener)
                            iot_device_1.disable_notifications(feature)
                        for idx, feature in enumerate(features2):
                            feature_listener = feature_listeners2[idx]
                            feature.remove_listener(feature_listener)
                            iot_device_2.disable_notifications(feature)
                                            
                        firmware_upgrade_completed = False
                        firmware_upgrade_started = False

                        # Disconnecting from the device.                            
                        for idx, device in enumerate(devices):
                            print('\nApp Disconnecting from %s...' % (device.get_name()))                           
                            device.remove_listener(node_listeners[idx])
                            device.disconnect()
                            send_disconnect_status(device, module_client)

                        print('Disconnection done.\n')
                        print('waiting for device to reboot....')
                        reboot = True
                        time.sleep(10)
                        print('after sleep...going to try to reconnect with device....')
                        break
                if iot_device_1.wait_for_notifications(0.05) or iot_device_2.wait_for_notifications(0.05):
                    # time.sleep(2) # workaround for Unexpected Response Issue
                    # print("rcvd notification!")
                    continue
        except (OSError, ValueError) as e:
                print("program Exception!")
                print(e)


# All Async operations
async def async_handler(module_client):
    global do_shadow_update, shadow_dict
    print("Async Handler....")
    while True:
        # print("$")        
        if do_shadow_update:
            print('async handler>> going to send reported properties...')
            await module_client.patch_twin_reported_properties(shadow_dict)
            print('async handler>> sent reported properties...')
            do_shadow_update = False
        
        # if pub_dev1:
        #     pub_dev1 = False
        #     print("going to publish device1 data....")
        #     #await module_client.publish(BLE1_APPMOD_OUTPUT, pub_string, 0)
        #     print("main async>> dev1 data published....")
        # if pub_dev2:
        #     pub_dev2 = False
        #     print("going to publish device2 data....")
        #     #await module_client.publish(BLE2_APPMOD_OUTPUT, pub_string, 0)
        #     print("main async>> dev2 data published....")
        await asyncio.sleep(0.05)

# define behavior for receiving direct method requests
async def method_request_listener(module_client):
    while True:
        print("awaiting method request listener")
        method_request = await module_client.receive_method_request(None)
        print("received method request")
        print(method_request)
        if method_request:
            print("received method request name: ")
            print(method_request.name)
            # TODO: Call appropriate method (E.g. firmwareUpdate, selectAIAlgorithm)
            status = 200
            payload = "{\"result\":\"success\"}"
            _response = MethodResponse.create_from_method_request(method_request, status, payload)
            await module_client.send_method_response(_response)
            print("sent method response")
        else:
            print("error in method request reception")
            

# Define behavior for receiving an input message on input1
# Because this is a filter module, we forward this message to the "output1" queue.
async def input1_listener(module_client):
    while True:
        try:
            input_message = await module_client.receive_message_on_input("input1")  # blocking call
            message = input_message.data
            size = len(message)
            message_text = message.decode('utf-8')
            print ( "    Data: <<<%s>>> & Size=%d" % (message_text, size) )
            custom_properties = input_message.custom_properties
            print ( "    Properties: %s" % custom_properties )            
        except Exception as ex:
            print ( "Unexpected error in input1_listener: %s" % ex )


# twin_patch_listener is invoked when the module twin's desired properties are updated.
async def twin_patch_listener(module_client):
    while True:
        try:
            data = await module_client.receive_twin_desired_properties_patch()  # blocking call
            print( "The data in the desired properties patch was: %s" % data)
        except Exception as ex:
            print ( "Unexpected error in twin_patch_listener: %s" % ex )


async def send_test_message(module_client):
    global count
    while True:
        await asyncio.sleep(5)
        count = count + 1
        print("sending message #" + str(count))
        # msg = "test wind speed " + str(count)
        msg = Message("test wind speed " + str(count))
        msg.message_id = uuid.uuid4()
        msg.correlation_id = "correlation-1234"
        msg.custom_properties["tornado-warning"] = "yes"
        await module_client.send_message_to_output(msg, BLE1_APPMOD_OUTPUT)
        print("done sending message #" + str(count))


def wait_for_dev_notifications():
    global iot_device_1, iot_device_2, ready

    print("Thread: Wait for notifications...")
    while True:
        print(">>>>>")
        time.sleep(10)


async def main():   

    try:
        if not sys.version >= "3.5.3":
            raise Exception( "The sample requires python 3.5.3+. Current version of Python: %s" % sys.version )
        print ( "\nSTM32MP1 module EW2020\n")
        print ( "\nPython %s\n" % sys.version )
        
        # initialize_client
        # module_client = AzureModuleClient(MODULE_NAME)
        module_client = IoTHubModuleClient.create_from_edge_environment()

        # Connecting clients to the runtime.
        print("going to connect to ModuleClient....")
        await module_client.connect()
        print("module connected to [%s]: [%s]..."% (MODULE_NAME, MODULEID))

        # Creating Bluetooth Manager.
        manager = Manager.instance()
        manager_listener = MyManagerListener()
        manager.add_listener(manager_listener)
        
        def stdin_listener():
            while True:
                try:
                    selection = input("Press Q to quit\n")
                    if selection == "Q" or selection == "q":
                        print("Quitting...")
                        break
                except:
                    time.sleep(5)

        # Run the stdin listener in the event loop
        # executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        loop = asyncio.get_event_loop()
        # await loop.run_in_executor(executor, main_method_sync, manager, module_client)        

        # Schedule task for listeners
        listeners = asyncio.gather(method_request_listener(module_client), async_handler(module_client))
        
        # Start thread to handle notifications
        notifications_task = threading.Thread(target=wait_for_dev_notifications)
        notifications_task.start()

        # Wait for user to indicate they are done listening for messages
        user_finished = loop.run_in_executor(None, ble_main_handler_sync, manager, module_client)
        await user_finished
        print("finished waiting for user input")

        # Cancel listening
        listeners.cancel()
        # Stop thread
        notifications_task.join()

        # Finally, disconnect
        await module_client.disconnect()                           

    except BTLEException as e:
        print(e)
        print('BTLEException...Exiting...\n')
        sys.exit(0)
    except KeyboardInterrupt:
        print ( "IoTHubModuleClient sample stopped" )

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()

    # asyncio.run(main())
