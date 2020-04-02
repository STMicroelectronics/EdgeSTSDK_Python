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
from azure.iot.device.aio import IoTHubModuleClient
from azure.iot.device import Message, MethodResponse

from edge_st_sdk.edge_client import EdgeClient
from edge_st_sdk.azure.azure_utils import CallbackContext

# CLASSES

class AzureModuleClient(EdgeClient):
    """Class responsible for handling an Azure Edge Module client used for MQTT/AMQP
    communication (Protocol Translation) with Azure IoT Hub"""

    _TIMEOUT_s = 10000
    """Timeout for messages"""
    _subscribe_callback = None
    _method_table = defaultdict(list)

    def __init__(self, module_name, protocol="MQTT"):
        self.module_name = module_name
        #self.client_protocol = protocol
        self.client = IoTHubModuleClient.create_from_edge_environment()
        self._connected = False       

    def get_name(self):
        return self.module_name

    async def connect(self):
        await self.client.connect()
         # set the time until a message times out
        #self.client.set_option("messageTimeout", self._TIMEOUT_s)
        self._connected = True
        return True

    async def disconnect(self):
        await self.client.disconnect()
        self._connected = False

    async def publish(self, topic, payload, qos):
        if self._connected:
            _msg = Message(payload)
            # msg.message_id = uuid.uuid4()
            # msg.correlation_id = "correlation-1234"
            # msg.custom_properties[""] = "yes"
            await self.client.send_message_to_output(_msg, topic)

    async def subscribe(self, topic, qos, callback):
        if self._connected:
            return await self.client.receive_message_on_input(topic)
        else:
            return None

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

    async def get_module_method_request(self, method_name=None):
        if self._connected:
            return self.client.receive_method_request(method_name)

    async def send_method_response(self, method_request, payload, status):
        if self._connected:
            _response = MethodResponse.create_from_method_request(method_request, status, payload)
            return await self.client.send_method_response(_response)

    # # Sets the callback when a module twin's desired properties are updated.
    # def set_module_twin_callback(self, twin_callback, user_context):
    #     if self._connected:
    #           ** self.client.receive_twin_desired_properties_patch()    
    #         self.client.set_module_twin_callback(twin_callback, user_context)
    
    def add_listener(self, listener):
        pass

    def remove_listener(self, listener):
        pass

    def _update_status(self, new_status):
        pass


    
# class AzureDeviceClient(EdgeClient):
#     """Class responsible for handling an Azure Edge Device client used for MQTT/AMQP
#     communication (for Identity Translation) with Azure IoT Hub"""

#     _TIMEOUT_s = 241000
#     _MESSAGE_TIMEOUT_s = 10000
#     _MINIMUM_POLLING_TIME_s = 9

#     """Timeout for messages"""
#     _subscribe_callback = None

#     def __init__(
#             self,
#             device_name,
#             connection_string,
#             protocol=IoTHubTransportProvider.MQTT):
#         self.device_name = device_name
#         self.client_protocol = protocol
#         self.client = IoTHubClient(connection_string, protocol)        
#         self._connected = False        

#     def get_name(self):
#         return self.device_name

#     def connect(self):
#         # not really a "connect"
#         if self.client_protocol == IoTHubTransportProvider.HTTP:
#             self.client.set_option("timeout", self._TIMEOUT_s)
#             self.client.set_option("MinimumPollingTime", self._MINIMUM_POLLING_TIME_s)
#         # set the time until a message times out
#         self.client.set_option("messageTimeout", self._MESSAGE_TIMEOUT_s)
#         self._connected = True
#         return True

#     def disconnect(self):
#         # not supported
#         self._connected = False

#     def publish(self, msg, msg_properties={}, send_confirmation_callback=None, send_context=0):
#         if self._connected:
#             if not isinstance(msg, IoTHubMessage):
#                 msg = IoTHubMessage(bytearray(msg, 'utf8'))
#             if len(msg_properties) > 0:
#                 prop_map = msg.properties()
#                 for key in msg_properties:
#                     prop_map.add_or_update(key, msg_properties[key])
#             self.client.send_event_async(
#                 msg, send_confirmation_callback, send_context)

#     def subscribe(self, callback=None, user_context=0):
#         if self._connected:
#             cbContext = CallbackContext(callback, user_context)
#             self.client.set_message_callback(self._subscribe_callback, cbContext)

#     def unsubscribe(self, topic):
#         # not supported
#         # set topic subsciption to null?
#         return

#     # Send Twin reported properties
#     def update_shadow_state(self, reported_state, callback=None, context=0):
#         if self._connected:    
#             self.client.send_reported_state(reported_state, len(reported_state), callback, context)

#     def get_shadow_state(self, callback, timeout_s):
#         # not supported
#         # get twin desired properties is however supported from the device services side (backend application)
#         return

#     def delete_shadow_state(self, callback, timeout_s):
#         # not supported
#         return

#     # Sets the callback when a module twin's desired properties are updated.
#     def set_device_twin_callback(self, twin_callback=None, user_context=0):
#         if self._connected:
#             self.client.set_device_twin_callback(twin_callback, user_context)

#     # Register a callback for module method
#     def set_device_method_callback(self, method_callback=None, user_context=0):
#         if self._connected:        
#             cbContext = CallbackContext(method_callback, user_context)
#             self.client.set_device_method_callback(self._method_callback, cbContext)
    
#     def set_certificates(self):
#         # from iothub_client_cert import CERTIFICATES
#         # try:
#         #     self.client.set_option("TrustedCerts", CERTIFICATES)
#         #     print ( "set_option TrustedCerts successful" )
#         # except IoTHubClientError as iothub_client_error:
#         #     print ( "set_option TrustedCerts failed (%s)" % iothub_client_error )
#         print ("not implemented")
#         pass

#     def upload_to_blob(self, destinationfilename, source, size, blob_upload_conf_callback=None, usercontext=0):
#         self.client.upload_blob_async(
#             destinationfilename, source, size,
#             blob_upload_conf_callback, usercontext)

#     # Internal callback for message which calls user callback
#     def _subscribe_callback(self, message, context):
#         callback = context._get_callback()
#         callback(message, context._get_context())
#         return IoTHubMessageDispositionResult.ACCEPTED
    
#     # Internal callback for method which calls user callback
#     def _method_callback(self, method_name, message, context):
#         callback = context._get_callback()
#         callback(method_name, message, context._get_context())
#         retval = DeviceMethodReturnValue()
#         retval.status = 200
#         retval.response = "{\"result\":\"success\"}"
#         return retval

#     def add_listener(self, listener):
#         pass

#     def remove_listener(self, listener):
#         pass

#     def _update_status(self, new_status):
#         pass
        
