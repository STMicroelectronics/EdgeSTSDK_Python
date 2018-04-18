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

from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTShadowClient

from edge_st_sdk.edge_client import EdgeClient
import edge_st_sdk.aws.aws_greengrass
from edge_st_sdk.utils.edge_st_exceptions import WrongInstantiationException


# CLASSES

class AWSClient(EdgeClient):
    """Class responsible for handling an Amazon AWS client used for plain MQTT
    communication with AWS IoT."""

    def __init__(self, client_id, device_certificate_path, \
        device_private_key_path, group_ca_path, core_info):
        """Constructor.

        Args:
            client_id (str): Name of the client, as it is on the cloud.
            device_certificate_path (str): Relative path of the device's
                certificate stored on the core device.
            device_private_key_path (str): Relative path of the device's
                private key stored on the core device.
            group_ca_path (str): Relative path of the certification authority's
                certificate stored on the core device.
            core_info (list): Information related to the core of the group to
                which the client belongs.

        Raises:
            :exc:`edge_st_sdk.utils.edge_st_exceptions.WrongInstantiationException`
                is raised if the discovery of the core has not been completed
                yet, i.e. if the AWSClient has not been instantiated through a
                call to the
                :meth:`edge_st_sdk.aws.aws_greengrass.AWSGreengrass.get_client`
                method.
        """
        # Check the client is created with the right pattern (Builder).
        if not edge_st_sdk.aws.aws_greengrass.AWSGreengrass.discovery_completed():
            raise WrongInstantiationException('Amazon AWS clients must be '
                'obtained through a call to the \'get_client()\' method of an '
                '\'AWSGreengrass\' object.')

        # Saving informations.
        self._connected = False
        self._client_id = client_id
        self._core_info = core_info
        
        # Creating a shadow client.
        self._shadow_client = AWSIoTMQTTShadowClient(client_id)
        self._shadow_client.configureCredentials(group_ca_path, device_private_key_path, device_certificate_path)

        # Getting the underneath client and configurint it.
        self._client = self._shadow_client.getMQTTConnection()
        self._client.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing.
        self._client.configureDrainingFrequency(2)  # Draining: 2 Hz.
        
        # Creating a shadow handler with persistent subscription.
        self._shadow_handler = self._shadow_client.createShadowHandlerWithName(self._client_id, True)

    def get_client_id(self):
        """Get the client identifier. 

        Returns:
            str: The client identifier, i.e. the name of the client.
        """
        return self._client_id

    def connect(self):
        """Connect to the core."""
        # Iterate through the connection options for the core and use the first
        # successful one.
        for connectivity_info in self._core_info.connectivityInfoList:
            self._current_host = connectivity_info.host
            self._current_port = connectivity_info.port
            print("Trying to connect to core at %s:%d..." % (self._current_host, self._current_port))
            self._shadow_client.configureEndpoint(self._current_host, self._current_port)
            self._shadow_client.configureAutoReconnectBackoffTime(1, 32, 20)
            self._shadow_client.configureConnectDisconnectTimeout(10)  # 10 sec
            self._shadow_client.configureMQTTOperationTimeout(5)  # 5 sec
            try:
                self._shadow_client.connect()
                self._connected = True
                break
            except BaseException as e:
                self._connected = False

        if not self._connected:
            print("Cannot connect to core %s. Exiting..." % self._core_info.coreThingArn)
            sys.exit(-2)
        else:
            print("Shadow device %s successfully connected to core %s." % (self._client_id, self._core_info.coreThingArn))

    def disconnect(self):
        """Disconnect from the core."""
        if self._connected:
            self._shadow_client.disconnect()

    def publish(self, topic, payload, qos):
        """Publish a new message to the desired topic with the given quality of
        service.

        Args:
            topic (str): Topic name to publish to.
            payload (str): Payload to publish (JSON formatted string).
            qos (int): Quality of Service. Could be "0" or "1".
        """
        if self._connected:
            self._client.publish(topic, payload, qos)

    def subscribe(self, topic, qos, callback):
        """Subscribe to the desired topic with the given quality of service and
        register a callback to handle the published messages.

        Args:
            topic (str): Topic name to publish to.
            qos (int): Quality of Service. Could be "0" or "1".
            callback: Function to be called when a new message for the
                subscribed topic comes in.
        """
        if self._connected:
            self._client.subscribe(topic, qos, callback)

    def unsubscribe(self, topic):
        """Unsubscribe to the desired topic.

        Args:
            topic (str): Topic name to unsubscribe to.
        """
        if self._connected:
            self._client.unsubscribe(topic)

    def get_shadow_state(self, callback, timeout_s):
        """Get the state of the shadow client.

        Retrieve the device shadow JSON document from the cloud by publishing an
        empty JSON document to the corresponding shadow topics.

        Args:
            callback: Function to be called when the response for a shadow
                request comes back.
            timeout_s (int): Timeout in seconds to perform the request.
        """
        if self._connected:
            self._shadow_handler.shadowGet(callback, timeout_s)

    def update_shadow_state(self, payload, callback, timeout_s):
        """Update the state of the shadow client.

        Update the device shadow JSON document string on the cloud by publishing
        the provided JSON document to the corresponding shadow topics.

        Args:
            payload (json): JSON document string used to update the shadow JSON
                document on the cloud.
            callback: Function to be called when the response for a shadow
                request comes back.
        """
        if self._connected:
            self._shadow_handler.shadowUpdate(payload, callback, timeout_s)

    def delete_shadow_state(self, callback, timeout_s):
        """Delete the state of the shadow client.
        
        Delete the device shadow from the cloud by publishing an empty JSON
        document to the corresponding shadow topics.

        Args:
            callback: Function to be called when the response for a shadow
                request comes back.
            timeout_s (int): Timeout in seconds to perform the request.
        """
        if self._connected:
            self._shadow_handler.shadowDelete(callback, timeout_s)
