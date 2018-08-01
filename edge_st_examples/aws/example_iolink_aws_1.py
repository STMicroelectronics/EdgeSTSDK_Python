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
# This application example shows how to connect IO-Link devices to a Linux
# gateway and to get data from them.


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
import serial
from serial import SerialException
from serial import SerialTimeoutException

from wire_st_sdk.iolink.iolink_master import IOLinkMaster
from wire_st_sdk.utils.wire_st_exceptions import InvalidOperationException

from edge_st_sdk.aws.aws_greengrass import AWSGreengrass
from edge_st_sdk.utils.edge_st_exceptions import WrongInstantiationException


# PRECONDITIONS
#
# Please remember to add to the "PYTHONPATH" environment variable the location
# of the "WireSTSDK_Python" and the "EdgeSTSDK_Python" SDKs.
#
# On Linux:
# export PYTHONPATH=/home/<user>/WireSTSDK_Python:/home/<user>/EdgeSTSDK_Python


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

# IO-Link settings.
SERIAL_PORT_NAME = '/dev/ttyUSB0'
SERIAL_PORT_BAUDRATE_bs = 230400

# Timeouts.
SHADOW_CALLBACK_TIMEOUT_s = 5
ENV_DATA_TIMEOUT_s = 10
TDM_DATA_TIMEOUT_s = 10
FFT_DATA_TIMEOUT_s = 20

# MQTT QoS.
MQTT_QOS_0 = 0
MQTT_QOS_1 = 1

# MQTT Topics.
MQTT_CONF_TOPIC = "iolink_device/configuration"
MQTT_ENV_TOPIC = "iolink_device/env_sense"
MQTT_TDM_TOPIC = "iolink_device/tdm_sense"
MQTT_FFT_TOPIC = "iolink_device/fft_sense"

# Devices' certificates, private keys, and path on the Linux gateway.
CERTIF_EXT = ".pem"
PRIV_K_EXT = ".prv"
DEVICES_PATH = "./devices_iolink_aws/"
IOT_DEVICE_1_NAME = '393832383035511900430037'
IOT_DEVICE_2_NAME = '3938323830355119003B0038'
IOT_DEVICE_1_CERTIF_PATH = DEVICES_PATH + IOT_DEVICE_1_NAME + CERTIF_EXT
IOT_DEVICE_2_CERTIF_PATH = DEVICES_PATH + IOT_DEVICE_2_NAME + CERTIF_EXT
IOT_DEVICE_1_PRIV_K_PATH = DEVICES_PATH + IOT_DEVICE_1_NAME + PRIV_K_EXT
IOT_DEVICE_2_PRIV_K_PATH = DEVICES_PATH + IOT_DEVICE_2_NAME + PRIV_K_EXT


# SHADOW JSON SCHEMAS

# {
#   "desired": {
#     "welcome": "aws-iot"
#   },
#   "reported": {
#     "welcome": "aws-iot"
#   }
# }


# STATIC JSON MESSAGES

# + HANDSHAKE (Upstream)
# "Board_Id": <string>,
# "Board_Type": <string>, --> Need a command in the FW]
# "Firmware": <string>,
# "Features": [n * <string>] --> To add "Temperature"

# + CONFIGURATION UPDATE (Downstream)
# "Board_Id": <string>,
# "FFT_Sampling_Rate": <int>,
# "FFT_Number_of_Samples": <int>,
# "FFT_Acquisition_Time": <?>,
# "Transmission_Time": <?>

# + THRESHOLDS UPDATE (Downstream)
# "Board_Id": <string>
# --> TBD


# DYNAMIC JSON MESSAGES

# + ENVIRONMENTAL (Upstream)
# "Board_Id": <string>,
# "Pressure": <float>,
# "Humidity": <float>,
# "Temperature": <float>

# + TIME DOMAIN (Upstream)
# "Board_Id": <string>,
# "Peak_Acceleration": [3 * <float>],
# "RMS_Speed": [3 * <float>]

# + VIBRATION (Upstream)
# "Board_Id": <string>,
# "FFT": ["FFT_Number_of_Samples" * [4 * <float>]


# CLASSES

# Index of the handshake data.
class HsIndex (Enum):
    BOARD_TYPE = 0
    FIRMWARE = 1
    FEATURES = 2

# Index of the environmental features.
class EnvIndex(Enum):
    PRESSURE = 0
    HUMIDITY = 1
    TEMPERATURE = 2

# Index of the time domain features.
class TdmIndex(Enum):
    RMS = 0
    PEAK = 1

# Index of the axes.
class AxesIndex(Enum):
    X = 0
    Y = 1
    Z = 2


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
        opts, args = getopt.getopt(argv,
            "hwe:k:c:r:", ['help", "endpoint=", "key=","cert=","rootCA='])
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
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    streamHandler.setFormatter(formatter)
    logger.addHandler(streamHandler)

#
# Setting the flag for getting environmental data.
#
def get_env(flag):
    global env_flags

    # Setting the flag for getting environmental data.
    env_flags[flag] = True

#
# Setting the flag for getting time domain data.
#
def get_tdm(flag):
    global tdm_flags

    # Setting the flag for getting time domain data.
    tdm_flags[flag] = True

#
# Setting the flag for getting Fast Fourier Transform of vibration data.
#
def get_fft(flag):
    global fft_flags

    # Setting the flag for getting Fast Fourier Transform of vibration data.
    fft_flags[flag] = True

#
# Publishing handshake data.
#
def publish_handshake(data, client, topic):
    #print('Device %d:' % (client.get_client_id()))
    #print('\tBoard_Type:\n\t\t\"%s\"' % (data[0]))
    #print('\tFirmware:\n\t\t\"%s\"' % (data[1]))
    #print('\tFeatures:\n\t\t%s' % (data[2]))

    # Getting a JSON representation of the message to publish.
    data_json = {
        "Board_Id": client.get_client_id(), 
        "Board_Type": str(data[HsIndex.BOARD_TYPE.value]), 
        "Firmware": str(data[HsIndex.FIRMWARE.value]), 
        "Features": str(data[HsIndex.FEATURES.value])
    }

    # Publishing the message.
    print('Publishing: %s' % (data_json))
    client.publish(topic, json.dumps(data_json), MQTT_QOS_0)

    # Udating shadow state.
    state_json = {
        "state": {
            "desired": data_json
        }
    }
    client.update_shadow_state(
        json.dumps(state_json),
        custom_shadow_callback_update,
        SHADOW_CALLBACK_TIMEOUT_s)

#
# Publishing environmental data.
#
def publish_env(data, client, topic):
    #print('Device %d:' % (client.get_client_id()))
    #print('\tEnvironmental data (P[mbar], H[%%], T[C]):\n\t\t%s' \
    #    % (data))

    # Getting a JSON representation of the message to publish.
    data_json = {
        "Board_Id": client.get_client_id(), 
        "Pressure": str(data[EnvIndex.PRESSURE.value]), 
        "Humidity": str(data[EnvIndex.HUMIDITY.value]), 
        "Temperature": str(data[EnvIndex.TEMPERATURE.value])
        # "ACC-X": "-1", 
        # "ACC-Y": "-1", 
        # "ACC-Z": "-1", 
        # "GYR-X": "-1", 
        # "GYR-Y": "-1", 
        # "GYR-Z": "-1", 
        # "MAG-X": "-1", 
        # "MAG-Y": "-1", 
        # "MAG-Z": "-1"
    }

    # Publishing the message.
    print('Publishing: %s' % (data_json))
    client.publish(topic, json.dumps(data_json), MQTT_QOS_0)

#
# Publishing time domain data.
#
def publish_tdm(data, client, topic):
    #print('Device %d:' % (client.get_client_id()))
    #print('\tTime domain data, RMS Speed [mm/s] and Peak Acceleration' \
    #    ' [m/s2]:\n\t\t%s' % (data))

    # Getting a JSON representation of the message to publish.
    data_json = {
        "Board_Id": client.get_client_id(), 
        "RMS_Speed": str(data[TdmIndex.RMS.value]),
        "Peak_Acceleration": str(data[TdmIndex.PEAK.value])
    }

    # Publishing the message.
    print('Publishing: %s' % (data_json))
    client.publish(topic, json.dumps(data_json), MQTT_QOS_0)

#
# Publishing Fast Fourier Transform of vibration data.
#
def publish_fft(data, client, topic):
    #print('Device %d:' % (client.get_client_id()))
    #print('\tFast Fourier Transform of vibration data [m/s2]:')
    #i = 0
    #for l in data:
    #    print('\t\t%d) %s' % (i, l))
    #    i += 1

    # Getting a JSON representation of the message to publish.
    data_json = {
        "Board_Id": client.get_client_id(), 
        "FFT": str(data)
    }

    # Publishing the message.
    item = data_json.items()[0]
    print('Publishing: {\'%s\': \'%s\', \'FFT\': \'[%d]\'}' \
        % (item[0], item[1], len(data)))
    client.publish(topic, json.dumps(data_json), MQTT_QOS_0)


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


#CLASSES

#
# Setting flag.
#
class FlagThread(threading.Thread):

    #
    # Constructor.
    #
    def __init__(self, function, flag, timeout):
        threading.Thread.__init__(self)
        self._function = function
        self._flag = flag
        self._timeout = timeout
        self.daemon = True

    #
    # Run the thread.
    #
    def run(self):
        while True:
            self._function(self._flag)
            time.sleep(self._timeout)


# MAIN APPLICATION

#
# Main application.
#
def main(argv):

    # Global variables.
    global endpoint, root_ca_path
    global env_flags, tdm_flags, fft_flags

    # Configure logging.
    configure_logging()

    # Printing intro.
    print_intro()

    # Reading input.
    read_input(argv)

    try:
        # Creating Serial Port.
        serial_port = serial.Serial()
        serial_port.port = SERIAL_PORT_NAME
        serial_port.baudrate = SERIAL_PORT_BAUDRATE_bs
        serial_port.parity = serial.PARITY_NONE
        serial_port.stopbits = serial.STOPBITS_ONE
        serial_port.bytesize = serial.EIGHTBITS
        serial_port.timeout = None

        # Creating an IO-Link Masterboard and connecting it to the host.
        print('Creating IO-Link Masterboard...\n')
        master = IOLinkMaster(serial_port)
        status = master.connect()
        print(status)

        # Getting IO-Link Devices.
        print('Creating IO-Link Devices...\n')
        devices = []
        devices.append(master.get_device(1))
        devices.append(master.get_device(2))

        # Checking setup.
        for device in devices:
            if not device:
                print('\nIO-Link setup incomplete. Exiting...\n')
                sys.exit(0)

        # IO-Link setup complete.
        print('IO-Link setup complete.\n')

        # Initializing Edge Computing.
        print('\nInitializing Edge Computing...\n')
        edge = AWSGreengrass(endpoint, root_ca_path)

        # Getting AWS MQTT clients.
        clients = []
        clients.append(edge.get_client(
            IOT_DEVICE_1_NAME,
            IOT_DEVICE_1_CERTIF_PATH,
            IOT_DEVICE_1_PRIV_K_PATH))
        clients.append(edge.get_client(
            IOT_DEVICE_2_NAME,
            IOT_DEVICE_2_CERTIF_PATH,
            IOT_DEVICE_2_PRIV_K_PATH))

        # Checking setup.
        for client in clients:
            if not client:
                print('\nAWS setup incomplete. Exiting...\n')
                sys.exit(0)

        # Connecting clients to the cloud.
        for client in clients:
            client.connect()

        # Sending handshake information.
        print('\nSending handshake information...\n')
        for i in range(0, len(devices)):
            # Getting data.
            data = []
            #data.append(devices[i].get_board_type())
            data.append("STEVAL-IPD005V1")
            data.append(devices[i].get_firmware())
            data.append(devices[i].get_features())

            # Publishing data.
            publish_handshake(data, clients[i], MQTT_CONF_TOPIC)

        # Edge Computing Initialized.
        print('\nEdge Computing setup complete.\n')

        # Sensors' flags.
        env_flags = [False] * len(devices)
        tdm_flags = [False] * len(devices)
        fft_flags = [False] * len(devices)

        # Starting threads.
        for i in range(0, len(devices)):
            FlagThread(get_env, i, ENV_DATA_TIMEOUT_s).start()
            FlagThread(get_tdm, i, TDM_DATA_TIMEOUT_s).start()
            FlagThread(get_fft, i, FFT_DATA_TIMEOUT_s).start()

        # Demo running.
        print('\nDemo running...\n')

        # Infinite loop.
        while True:
            for i in range(0, len(devices)):
                if env_flags[i]:
                    # Getting data.
                    data = devices[i].get_env()

                    # Publishing data.
                    publish_env(data, clients[i], MQTT_ENV_TOPIC)

                    # Resetting flag.
                    env_flags[i] = False

                elif tdm_flags[i]:
                    # Getting data.
                    data = devices[i].get_tdm()

                    # Publishing data.
                    publish_tdm(data, clients[i], MQTT_TDM_TOPIC)

                    # Resetting flag.
                    tdm_flags[i] = False

                elif fft_flags[i]:
                    # Getting data.
                    data = devices[i].get_fft()

                    # Publishing data.
                    publish_fft(data, clients[i], MQTT_FFT_TOPIC)

                    # Resetting flag.
                    fft_flags[i] = False


    except WrongInstantiationException as e:
        print(e)
        master.disconnect()
        print('Exiting...\n')
        sys.exit(0)
    except (SerialException, SerialTimeoutException, \
        InvalidOperationException) as e:
        print(e)
        master.disconnect()
        print('Exiting...\n')
        sys.exit(0)
    except KeyboardInterrupt:
        try:
            master.disconnect()
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
