################################################################################
# COPYRIGHT(c) 2020 STMicroelectronics                                         #
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


"""azure_client
The azure_client module represents a client capable of connecting to the Microsoft
IoT Hub and performing edge operations through the azure-iot-sdk (python).
"""


# IMPORT

import sys
import asyncio
from collections import defaultdict
import azure.iot.device.aio
# pylint: disable=E0611
from azure.iot.device.aio import IoTHubModuleClient, IoTHubDeviceClient
from azure.iot.device import Message, MethodResponse

from edge_st_sdk.edge_client import EdgeClient
from edge_st_sdk.azure.azure_utils import CallbackContext

# CLASSES

class AzureClient(EdgeClient):
    """Class responsible for handling an Azure Edge Module and Device client used for MQTT/AMQP
    communication (Protocol Translation) with Azure IoT Hub"""

    def __init__(self, name="", conn_str=None):
        self._name = name
        if conn_str:
            self.client = IoTHubDeviceClient.create_from_connection_string(conn_str)
        else:
            self.client = IoTHubModuleClient.create_from_edge_environment()
        self._connected = False

    def get_name(self):
        return self._name

    async def connect(self):
        await self.client.connect()
        self._connected = True
        return True

    async def disconnect(self):
        await self.client.disconnect()
        self._connected = False

    async def publish(self, topic=None, payload=""):
        if self._connected:
            _msg = Message(payload)
            # msg.message_id = uuid.uuid4()
            # msg.correlation_id = "correlation-1234"
            # msg.custom_properties[""] = "yes"
            if topic:
                await self.client.send_message_to_output(_msg, topic)
            else:
                await self.client.send_message(_msg)

    async def subscribe(self, topic=None):
        if self._connected:
            if topic:
                return await self.client.receive_message_on_input(topic)
            else:
                return await self.client.receive_message()

    async def unsubscribe(self, topic):
        # not supported
        # set topic subsciption to null?
        return

    # Send Twin "reported" properties
    async def update_shadow_state(self, payload, callback, timeout_s):
        if self._connected:
            return await self.client.patch_twin_reported_properties(payload)

    # Receive Twin "desired" properties
    async def get_shadow_state(self, callback, timeout_s):
        if self._connected:
            return await self.client.receive_twin_desired_properties_patch()

    async def delete_shadow_state(self, callback, timeout_s):
        # not supported
        return

    async def get_method_request(self, method_name=None):
        if self._connected:
            return await self.client.receive_method_request(method_name)

    async def send_method_response(self, method_request, payload, status):
        if self._connected:
            _response = MethodResponse.create_from_method_request(method_request, status, payload)
            return await self.client.send_method_response(_response)

    def add_listener(self, listener):
        pass

    def remove_listener(self, listener):
        pass

    def _update_status(self, new_status):
        pass

