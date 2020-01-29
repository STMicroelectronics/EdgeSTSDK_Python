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
from edge_st_sdk.azure.azure_client import AzureModuleClient
from blue_st_sdk.ai_algos.ai_algos import AIAlgos, AIAlgosDebugConsoleListener
from blue_st_sdk.utils.message_listener import MessageListener
from edge_st_sdk.utils.edge_st_exceptions import EdgeSTInvalidOperationException, EdgeSTInvalidDataException

from ble_helper import *

# Firmware file paths.
FIRMWARE_PATH = '/app/'
FIRMWARE_EXTENSION = '.bin'

BLE1_APPMOD_INPUT   = 'BLE1_App_Input'
BLE1_APPMOD_OUTPUT  = 'BLE1_App_Output'
BLE2_APPMOD_INPUT   = 'BLE2_App_Input'
BLE2_APPMOD_OUTPUT  = 'BLE2_App_Output'

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

        json_string = json.dumps(reported_json)
        self.module_client.update_shadow_state(json_string, send_reported_state_callback, self.module_client)
        print('sent reported properties...with status "connected"')


    def on_disconnect(self, node, unexpected=False):
        global iot_device_1
        print('Device %s disconnected%s.' % \
            (node.get_name(), ' unexpectedly' if unexpected else ''))

        reported_json = {
                "devices": {
                    node.get_name(): {
                        "State": {
                            "ble_conn_status": "disconnected"
                        }
                }
            }
        }
        json_string = json.dumps(reported_json)
        self.module_client.update_shadow_state(json_string, send_reported_state_callback, self.module_client)
        print('sent reported properties...with status "disconnected"')

        if unexpected:
            #iot_device_1.remove_listener(node_listener)            
            print('\nApp Disconnecting from %s...' % (node.get_name()))
            node.disconnect()
            print('Disconnection done.\n')
            # Exiting.
            print('\non_disconnect Exiting...\n')
            sys.exit(0)

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
        global firmware_status, firmware_update_file
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
        global firmware_upgrade_completed, fwup_error
        global firmware_status, firmware_update_file
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

        json_string = json.dumps(reported_json)
        self.module_client.update_shadow_state(json_string, send_reported_state_callback, self.module_client)
        print('sent reported properties...with status "fail"')
        # time.sleep(5)
        firmware_upgrade_completed = True
        fwup_error = True
        # Exiting.
        print('\nExiting...module will re-start\n')
        sys.exit(0)

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
    global iot_device_1
    global AI_AlgoNames, AI_console, setAIAlgo, algo_name, har_algo, start_algo
    print('received method call:')
    print('method name:', method_name)
    print('payload:', payload)
    json_dict = json.loads(payload)
    print ('AI Algo to set:')
    algo_name = json_dict['Name']
    start_algo = 'har' #MPD: TBD use : json_dict['start_algo']
    # Assumption: Algo name is in format "ASC+HAR", hence HAR algo is always split('+')[1]
    har_algo = algo_name.split('+')[1].lower()
    print ('algo name: ' + algo_name)
    print ('har algo: ' + har_algo)
    print ('start algo: ' + start_algo)
    setAIAlgo = True
    return

class MyFeatureListener(FeatureListener):

    num = 0
    
    def __init__(self, azureClient, node):
        self.module_client = azureClient
        self.device = node

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
            "nodeId": self.device.get_name(),
            "aiEventType": aiEventType,
            "aiEvent": aiEvent,
            "ts": event_timestamp.replace(tzinfo=simple_utc()).isoformat().replace('+00:00', 'Z')
        }
        json_string = json.dumps(event_json)
        print(json_string)
        if self.device.get_tag() == IOT_DEVICE_1_MAC:
            self.module_client.publish(BLE1_APPMOD_OUTPUT, json_string, send_confirmation_callback, 0)
        elif self.device.get_tag() == IOT_DEVICE_2_MAC:
            self.module_client.publish(BLE2_APPMOD_OUTPUT, json_string, send_confirmation_callback, 0)
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
    global firmware_status
    print ( "\nModule twin callback >> call confirmed\n")
    print('\tpayload:', payload)


def send_reported_state_callback(status_code, context):
    print ( "\nSend reported state callback >> call confirmed\n")
    print ('status code: ', status_code)
    pass


def main(protocol):   

    try:
        print ( "\nSTM32MP1 module EW2020\n")
        print ( "\nPython %s\n" % sys.version )

        # Global variables.
        global iot_device_1, iot_device_2        
        global firmware_upgrade_completed
        global firmware_upgrade_started
        global firmware_status
        global firmware_update_file
        global firmware_desc
        global features1, features2, feature_listener1, feature_listener2, feature_listeners1, feature_listeners2, no_wait
        global upgrade_console, upgrade_console_listener, fwup_error, update_node
        global AIAlgo_msg_process, AIAlgo_msg_completed, AI_msg
        global AI_AlgoNames, AI_console, setAIAlgo, algo_name, har_algo, start_algo
        
        # initialize_client
        module_client = AzureModuleClient(MODULE_NAME, PROTOCOL)

        # Connecting clients to the runtime.
        module_client.connect()
        module_client.set_module_twin_callback(module_twin_callback, module_client)
        module_client.set_module_method_callback(firmwareUpdate, module_client)      
        module_client.set_module_method_callback(selectAIAlgorithm, module_client)  
        module_client.subscribe(BLE1_APPMOD_INPUT, receive_ble1_message_callback, module_client)        
        module_client.subscribe(BLE2_APPMOD_INPUT, receive_ble2_message_callback, module_client)

        # Initial state.
        firmware_upgrade_completed = False
        firmware_upgrade_started = False
        no_wait = False
        fwup_error = False
        AIAlgo_msg_completed = False
        AIAlgo_msg_process = False
        AI_msg = "None"
        AI_AlgoNames = {}
        setAIAlgo = False
        reboot = False
        update_node = None
        feature_listeners1 = []
        feature_listeners2 = []

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

            if reboot:
                reboot = False
            
            timeout = time.time() + 10
            AIAlgo_msg_process = True
            AI_console1.getAIAllAlgoDetails()
            while True:
                if iot_device_1.wait_for_notifications(0.05):
                    continue
                elif AIAlgo_msg_completed:                    
                    print("Algos received:" + AI_msg)
                    break
                elif time.time() > timeout:                    
                    print("no response for AIAlgos cmd")
                    break
            AIAlgo_msg_process = False
            AIAlgo_msg_completed = False

            algos_supported, AI_AlgoNames = extract_algo_details(AI_msg)

            firmware_status = ai_fw_running1
            print("firmware reported by node: " + ai_fw_running1)
            reported_json = compile_reported_props_from_node(devices[0].get_name(), ai_fw_running1, firmware_desc1, algos_supported)
            # FIXME we are using the same algos_supported of device 1 for device 2.
            _reported_json = compile_reported_props_from_node(devices[1].get_name(), ai_fw_running2, firmware_desc2, algos_supported)
            reported_json["devices"].update(_reported_json["devices"])

            json_string = json.dumps(reported_json)
            module_client.update_shadow_state(json_string, send_reported_state_callback, module_client)
            print('sent reported properties...')

            # Getting notifications about firmware events
            print('\nWaiting for event notifications...\n')        
            # feature = features[0]

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
            print('\nDemo running (\"CTRL+C\" to quit)...\n')        

            try:
                while True:
                    if setAIAlgo:
                        setAIAlgo = False
                        AI_console1.setAIAlgo(AI_AlgoNames[algo_name], har_algo, start_algo)
                        continue
                    if no_wait:
                        no_wait = False
                        # print('update node:' + update_node)
                        if update_node and update_node == iot_device_1.get_name():
                            print("prep'ing device 1")
                            prepare_listeners_for_fwupdate(iot_device_1, features1, feature_listeners1, AI_console1, 
                                                        upgrade_console_listener1, upgrade_console1)
                        elif update_node and update_node == iot_device_2.get_name():
                            print("prep'ing device 2")
                            prepare_listeners_for_fwupdate(iot_device_2, features2, feature_listeners2, AI_console2, 
                                                        upgrade_console_listener2, upgrade_console2)

                        firmware_upgrade_completed = False
                        firmware_upgrade_started = True

                        if update_node and update_node == iot_device_1.get_name():
                            print("updating device 1")
                            if not start_device_fwupdate(upgrade_console1, firmware_update_file, fwup_error):
                                break
                        elif update_node and update_node == iot_device_2.get_name():
                            print("updating device 2")
                            if not start_device_fwupdate(upgrade_console2, firmware_update_file, fwup_error):
                                break

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

                        json_string = json.dumps(reported_json)
                        module_client.update_shadow_state(json_string, send_reported_state_callback, module_client)
                        print('sent reported properties...with status "running"')

                        while not firmware_upgrade_completed:
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

    except BTLEException as e:
        print(e)
        print('BTLEException...Exiting...\n')
        sys.exit(0)        
    except IoTHubError as iothub_error:
        print ( "Unexpected error %s from IoTHub" % iothub_error )
        return
    except KeyboardInterrupt:
        print ( "IoTHubModuleClient sample stopped" )

if __name__ == '__main__':
    main(PROTOCOL)
