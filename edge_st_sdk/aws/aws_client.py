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


"""aws_client

The aws_client module represents a client capable of connecting to the Amazon
AWS IoT cloud and performing edge operations through the Greengrass SDK.
"""


# IMPORT

import sys
from concurrent.futures import ThreadPoolExecutor

from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTShadowClient

from edge_st_sdk.utils.python_utils import lock
from edge_st_sdk.edge_client import EdgeClient
from edge_st_sdk.edge_client import EdgeClientStatus
import edge_st_sdk.aws.aws_greengrass
from edge_st_sdk.utils.edge_st_exceptions import EdgeSTInvalidOperationException


# CLASSES

class AWSClient(EdgeClient):
    """Class responsible for handling an Amazon AWS client used for plain MQTT
    communication with AWS IoT."""

    _TIMEOUT_s = 10
    """Timeout for discovering information."""

    _NUMBER_OF_THREADS = 5
    """Number of threads to be used to notify the listeners."""

    def __init__(self, client_name, device_certificate_path, \
        device_private_key_path, group_ca_path, core_info):
        """Constructor.

        AWSClient has to be instantiated through a call to the
        :meth:`edge_st_sdk.aws.aws_greengrass.AWSGreengrass.get_client` method.

        :param client_name: Name of the client, as it is on the cloud.
        :type client_name: str

        :param device_certificate_path: Relative path of the device's
            certificate stored on the core device.
        :type device_certificate_path: str

        :param device_private_key_path: Relative path of the device's private
            key stored on the core device.
        :type device_private_key_path: str

        :param group_ca_path: Relative path of the certification authority's
            certificate stored on the core device.
        :type group_ca_path: str

        :param core_info: Information related to the core of the group to which
            the client belongs.
        :type core_info: list

        :raises EdgeSTInvalidOperationException: is raised if the discovery of
            the core has not been completed yet, i.e. if the AWSClient has not
            been instantiated through a call to the
            :meth:`edge_st_sdk.aws.aws_greengrass.AWSGreengrass.get_client`
            method.
        """
        self._status = EdgeClientStatus.INIT
        """Status."""

        self._thread_pool = ThreadPoolExecutor(AWSClient._NUMBER_OF_THREADS)
        """Pool of thread used to notify the listeners."""

        self._listeners = []
        """List of listeners to the feature changes.
        It is a thread safe list, so a listener can subscribe itself through a
        callback."""

        # Check the client is created with the right pattern (Builder).
        if not edge_st_sdk.aws.aws_greengrass.AWSGreengrass.discovery_completed():
            raise EdgeSTInvalidOperationException('Amazon AWS clients must be ' \
                'obtained through a call to the \'get_client()\' method of an ' \
                '\'AWSGreengrass\' object.')

        # Saving informations.
        self._connected = False
        self._client_name = client_name
        self._core_info = core_info
        
        # Creating a shadow client.
        self._shadow_client = AWSIoTMQTTShadowClient(client_name)
        self._shadow_client.configureCredentials(
            group_ca_path,
            device_private_key_path,
            device_certificate_path)

        # Getting the underneath client and configurint it.
        self._client = self._shadow_client.getMQTTConnection()
        self._client.configureOfflinePublishQueueing(-1)  # Infinite queueing.
        self._client.configureDrainingFrequency(2)  # Draining: 2 Hz.
        
        # Creating a shadow handler with persistent subscription.
        self._shadow_handler = self._shadow_client.createShadowHandlerWithName(
            self._client_name, True)

        # Updating client.
        self._update_status(EdgeClientStatus.IDLE)

    def get_name(self):
        """Get the client name. 

        :returns: The client name, i.e. the name of the client.
        :rtype: str
        """
        return self._client_name

    def connect(self):
        """Connect to the core.

        :returns: True if the connection was successful, False otherwise.
        :rtype: bool
        """
        # Updating client.
        self._update_status(EdgeClientStatus.CONNECTING)

        # Connecting.
        if not self._connected:
            # Iterate through the connection options for the core and use the
            # first successful one.
            for connectivity_info in self._core_info.connectivityInfoList:
                self._current_host = connectivity_info.host
                self._current_port = connectivity_info.port
                self._shadow_client.configureEndpoint(
                    self._current_host,
                    self._current_port)
                self._shadow_client.configureAutoReconnectBackoffTime(1, 32, 20)
                self._shadow_client.configureConnectDisconnectTimeout(
                    self._TIMEOUT_s)
                self._shadow_client.configureMQTTOperationTimeout(
                    self._TIMEOUT_s / 2.0)
                try:
                    self._shadow_client.connect()
                    self._connected = True
                    break
                except BaseException as e:
                    self._connected = False
        if self._connected:
            self._update_status(EdgeClientStatus.CONNECTED)
        else:
            self._update_status(EdgeClientStatus.UNREACHABLE)

        return self._connected

    def disconnect(self):
        """Disconnect from the core."""
        # Updating client.
        self._update_status(EdgeClientStatus.DISCONNECTING)

        # Disconnecting.
        if self._connected:
            self._shadow_client.disconnect()
            self._connected = False

        # Updating client.
        self._update_status(EdgeClientStatus.DISCONNECTED)

    def publish(self, topic, payload, qos):
        """Publish a new message to the desired topic with the given quality of
        service.

        :param topic: Topic name to publish to.
        :type topic: str

        :param payload: Payload to publish (JSON formatted string).
        :type payload: str

        :param qos: Quality of Service. Could be "0" or "1".
        :type qos: int
        """
        if self._connected:
            self._client.publish(topic, payload, qos)

    def subscribe(self, topic, qos, callback):
        """Subscribe to the desired topic with the given quality of service and
        register a callback to handle the published messages.

        :param topic: Topic name to publish to.
        :type topic: str

        :param qos: Quality of Service. Could be "0" or "1".
        :type qos: int

        :param callback: Function to be called when a new message for the
            subscribed topic comes in.
        """
        if self._connected:
            self._client.subscribe(topic, qos, callback)

    def unsubscribe(self, topic):
        """Unsubscribe to the desired topic.

        :param topic: Topic name to unsubscribe to.
        :type topic: str
        """
        if self._connected:
            self._client.unsubscribe(topic)

    def get_shadow_state(self, callback, timeout_s):
        """Get the state of the shadow client.

        Retrieve the device shadow JSON document from the cloud by publishing an
        empty JSON document to the corresponding shadow topics.

        :param callback: Function to be called when the response for a shadow
            request comes back.

        :param timeout_s: Timeout in seconds to perform the request.
        :type timeout_s: int
        """
        if self._connected:
            self._shadow_handler.shadowGet(callback, timeout_s)

    def update_shadow_state(self, payload, callback, timeout_s):
        """Update the state of the shadow client.

        Update the device shadow JSON document string on the cloud by publishing
        the provided JSON document to the corresponding shadow topics.

        :param payload: JSON document string used to update the shadow JSON
            document on the cloud.
        :type payload: json

        :param callback: Function to be called when the response for a shadow
            request comes back.

        :param timeout_s: Timeout in seconds to perform the request.
        :type timeout_s: int
        """
        if self._connected:
            self._shadow_handler.shadowUpdate(payload, callback, timeout_s)

    def delete_shadow_state(self, callback, timeout_s):
        """Delete the state of the shadow client.
        
        Delete the device shadow from the cloud by publishing an empty JSON
        document to the corresponding shadow topics.

        :param callback: Function to be called when the response for a shadow
            request comes back.

        :param timeout_s: Timeout in seconds to perform the request.
        :type timeout_s: int
        """
        if self._connected:
            self._shadow_handler.shadowDelete(callback, timeout_s)

    def add_listener(self, listener):
        """Add a listener.
        
        :param listener: Listener to be added.
        :type listener: :class:`edge_st_sdk.edge_client.EdgeClientListener`
        """
        if listener is not None:
            with lock(self):
                if not listener in self._listeners:
                    self._listeners.append(listener)

    def remove_listener(self, listener):
        """Remove a listener.

        :param listener: Listener to be removed.
        :type listener: :class:`edge_st_sdk.edge_client.EdgeClientListener`
        """
        if listener is not None:
            with lock(self):
                if listener in self._listeners:
                    self._listeners.remove(listener)

    def _update_status(self, new_status):
        """Update the status of the client.

        :param new_status: New status.
        :type new_status: :class:`edge_st_sdk.edge_client.EdgeClientStatus`
        """
        old_status = self._status
        self._status = new_status
        for listener in self._listeners:
            # Calling user-defined callback.
            self._thread_pool.submit(
                listener.on_status_change(
                    self, new_status.value, old_status.value))
