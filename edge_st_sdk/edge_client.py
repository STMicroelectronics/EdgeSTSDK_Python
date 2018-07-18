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


"""edge_client

The edge_client module contains an interface for creating edge client classes.
"""


# IMPORT

from abc import ABCMeta
from abc import abstractmethod


# INTERFACE

class EdgeClient(object):
    """The EdgeClient class is an interface for creating edge client classes."""
    __metaclass__ = ABCMeta

    @abstractmethod
    def connect(self):
        """Connect to the core."""
        raise NotImplementedError('You must define "connect()" to use the "EdgeClient" class.')

    @abstractmethod
    def disconnect(self):
        """Disconnect from the core."""
        raise NotImplementedError('You must define "disconnect()" to use the "EdgeClient" class.')

    @abstractmethod
    def publish(self, topic, payload, qos):
        """Publish a new message to the desired topic with the given quality of
        service.

        Args:
            topic (str): Topic name to publish to.
            payload (str): Payload to publish (JSON formatted string).
            qos (int): Quality of Service. Could be "0" or "1".
        """
        raise NotImplementedError('You must define "publish()" to use the "EdgeClient" class.')

    @abstractmethod
    def subscribe(self, topic, qos, callback):
        """Subscribe to the desired topic with the given quality of service and
        register a callback to handle the published messages.

        Args:
            topic (str): Topic name to publish to.
            qos (int): Quality of Service. Could be "0" or "1".
            callback: Function to be called when a new message for the
                subscribed topic comes in.
        """
        raise NotImplementedError('You must define "subscribe()" to use the "EdgeClient" class.')

    @abstractmethod
    def unsubscribe(self, topic):
        """Unsubscribe to the desired topic.

        Args:
            topic (str): Topic name to unsubscribe to.
        """
        raise NotImplementedError('You must define "unsubscribe()" to use the "EdgeClient" class.')

    @abstractmethod
    def get_shadow_state(self, callback, timeout_s):
        """Get the state of the shadow client.

        Retrieve the device shadow JSON document from the cloud by publishing an
        empty JSON document to the corresponding shadow topics.

        Args:
            callback: Function to be called when the response for a shadow
                request comes back.
            timeout_s (int): Timeout in seconds to perform the request.
        """
        raise NotImplementedError('You must define "get_shadow()" to use the "EdgeClient" class.')

    @abstractmethod
    def update_shadow_state(self, payload, callback, timeout_s):
        """Update the state of the shadow client.

        Update the device shadow JSON document string on the cloud by publishing
        the provided JSON document to the corresponding shadow topics.

        Args:
            payload (json): JSON document string used to update the shadow JSON
                document on the cloud.
            callback: Function to be called when the response for a shadow
                request comes back.
            timeout_s (int): Timeout in seconds to perform the request.
        """
        raise NotImplementedError('You must define "update_shadow()" to use the "EdgeClient" class.')

    @abstractmethod
    def delete_shadow_state(self, callback, timeout_s):
        """Delete the state of the shadow client.
        
        Delete the device shadow from the cloud by publishing an empty JSON
        document to the corresponding shadow topics.

        Args:
            callback: Function to be called when the response for a shadow
                request comes back.
            timeout_s (int): Timeout in seconds to perform the request.
        """
        raise NotImplementedError('You must define "delete_shadow()" to use the "EdgeClient" class.')
