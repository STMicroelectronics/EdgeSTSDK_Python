
import time

from blue_st_sdk.manager import Manager, ManagerListener
from blue_st_sdk.node import NodeListener
from blue_st_sdk.feature import FeatureListener
from blue_st_sdk.features import *
from blue_st_sdk.firmware_upgrade.firmware_upgrade_nucleo import FirmwareUpgradeNucleo
from blue_st_sdk.firmware_upgrade.firmware_upgrade import FirmwareUpgradeListener
from blue_st_sdk.firmware_upgrade.utils.firmware_file import FirmwareFile
from blue_st_sdk.features.feature_activity_recognition import ActivityType as act
from blue_st_sdk.features.feature_audio_scene_classification import SceneType as scene


def extract_algo_details(AI_algo_details=''):
    algos_supported=''
    AI_AlgoNames = []
    res = AI_algo_details.split('\n')
    for t in range(len(res)):
        if res[t] == '':
            continue
        algos_supported += res[t]
        algos_supported += ';'

        __har = res[t].split('-')
        if len(__har) > 1:
            _algo = __har[0].strip()
            AI_AlgoNames[_algo] = t+1
    return algos_supported, AI_AlgoNames

def compile_reported_props_from_node(node, ai_fw_running, firmware_desc, algos_supported):
    reported_json = {
                "devices": {
                    node: {
                        "SupportedMethods": {
                            "firmwareUpdate--FwPackageUri-string": "Updates device firmware. Use parameter FwPackageUri to specify the URL of the firmware file",
                            "selectAIAlgorithm--Name-string": "Select AI algorithm to run on device. Use parameter Name to specify AI algo to set on device"
                        },
                        "AI": {
                            "firmware": ai_fw_running,
                            "algorithms": algos_supported
                        },
                        "State": {
                            "fw_update": "Not_Running"
                        }
                    }
                }
            }
    for fw, desc in firmware_desc.items():
        reported_json["devices"][node]["AI"].update({fw:desc})
    return reported_json

def extract_ai_features_from_node(node):
    i = 1
    features = []
    ai_fw_running = ''
    firmware_desc = {}
    for desired_feature in [
                feature_audio_scene_classification.FeatureAudioSceneClassification,
                feature_activity_recognition.FeatureActivityRecognition]:
                feature = node.get_feature(desired_feature)
                if feature:
                    features.append(feature)
                    print('%d) %s' % (i, feature.get_name()))
                    if i == 2:
                        ai_fw_running += ';'
                    if feature.get_name() == "Activity Recognition":
                        ai_fw_running += "activity-recognition"
                        firmware_desc["activity-recognition"] = "stationary;walking;jogging;biking;driving;stairs"
                    elif feature.get_name() == "Audio Scene Classification":
                        ai_fw_running += "audio-classification"
                        firmware_desc["audio-classification"] = "in-door;out-door;in-vehicle"                    
                    i += 1
    if not features:
        print('No features found on node %s' % (node.get_name()))
    print('%d) Firmware upgrade' % i) # Print this by default, assuming that FW Upgrade is part of features
    return features, ai_fw_running, firmware_desc


def prepare_listeners_for_fwupdate(node, features, feature_listeners, ai_console, fw_listener, fw_console):
    print("Stopping all Algos")
    ai_console.stopAlgos()
    time.sleep(1)

    for idx, feature in enumerate(features):
        node.disable_notifications(feature)
        feature_listener = feature_listeners[idx]
        feature.remove_listener(feature_listener)

    fw_console.add_listener(fw_listener)
    return


def start_device_fwupdate(fw_console, file, fwup_error, _timeout = 2):
    
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


def update_reported_properties():
    return