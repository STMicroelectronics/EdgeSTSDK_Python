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


"""aws_greengrass

The aws_greengrass module is responsible for managing the discovery process of
AWS devices and allocating the needed resources.

"""


# IMPORT

import os
import sys
import uuid
import logging

from AWSIoTPythonSDK.core.greengrass.discovery.providers import DiscoveryInfoProvider
from AWSIoTPythonSDK.core.protocol.connection.cores import ProgressiveBackOffCore
from AWSIoTPythonSDK.exception.AWSIoTExceptions import DiscoveryInvalidRequestException

import edge_st_sdk.aws.aws_client


# CLASSES

class AWSGreengrass(object):

    MAX_DISCOVERY_ATTEMPTS = 10
    """Maximum number of attempts when trying to discover the core."""

    _GROUP_CA_PATH  = "./aws_group_ca/"
    """Group Certification Authority path.""" 

    _discovery_completed = False
    """Discovery completed flag."""

    def __init__(self, endpoint, root_ca_path):
        """Constructor.

        Initializing AWS Discovery.

        Args:
            endpoint (str): AWS endpoint.
            root_ca_path (str): Path to the root Certification Authority file. 
        """
        self._endpoint = endpoint
        self._root_ca_path = root_ca_path
        self._group_ca_path = None
        self._core_info = None

    def _discover_core(self, client_id, device_certificate_path, device_private_key_path):
        """Performing the discovery of the core belonging to the same group of
        the given client identifier.

        Args:
            client_id (str): Name of a client, as it is on the cloud, belonging
                to the same group of the core.
            device_certificate_path (str): Relative path of a device's
                certificate stored on the core device, belonging to the same
                group of the core.
            device_private_key_path (str): Relative path of a device's
                private key stored on the core device, belonging to the same
                group of the core.
        """

        # Progressive back off core
        backOffCore = ProgressiveBackOffCore()

        # Discover GGCs
        discoveryInfoProvider = DiscoveryInfoProvider()
        discoveryInfoProvider.configureEndpoint(self._endpoint)
        discoveryInfoProvider.configureCredentials(self._root_ca_path, device_certificate_path, device_private_key_path)
        discoveryInfoProvider.configureTimeout(10)  # 10 sec
        retryCount = self.MAX_DISCOVERY_ATTEMPTS
        discovered = False

        while retryCount != 0:
            try:
                discoveryInfo = discoveryInfoProvider.discover(client_id)
                caList = discoveryInfo.getAllCas()
                coreList = discoveryInfo.getAllCores()
                # We only pick the first ca and core info
                groupId, ca = caList[0]
                self._core_info = coreList[0]
                print("Discovered GGC: %s from Group: %s" % (self._core_info.coreThingArn, groupId))

                print("Now we persist the connectivity/identity information...")
                self._group_ca_path = self._GROUP_CA_PATH + groupId + "_CA_" + str(uuid.uuid4()) + ".crt"
                if not os.path.exists(self._GROUP_CA_PATH):
                    os.makedirs(self._GROUP_CA_PATH)
                group_ca_path_file = open(self._group_ca_path, "w")
                group_ca_path_file.write(ca)
                group_ca_path_file.close()
                discovered = True
                print("Now proceed to the connecting flow...")
                break
            except DiscoveryInvalidRequestException as e:
                print("Invalid discovery request detected!")
                print("Type: %s" % str(type(e)))
                print("Error message: %s" % e.message)
                print("Stopping...")
                break
            except BaseException as e:
                print("Error in discovery!")
                print("Type: %s" % str(type(e)))
                print("Error message: %s" % e.message)
                retryCount -= 1
                print("\n%d/%d retries left\n" % (retryCount, self.MAX_DISCOVERY_ATTEMPTS))
                print("Backing off...\n")
                backOffCore.backOff()

        if not discovered:
            print("Discovery failed after %d retries. Exiting...\n" % (self.MAX_DISCOVERY_ATTEMPTS))
            sys.exit(-1)

        self._configure_logging()
        AWSGreengrass._discovery_completed = True

    def _configure_logging(self):
        """Configure logging, required for using shadow devices."""
        self._logger = logging.getLogger("AWSIoTPythonSDK.core")
        self._logger.setLevel(logging.ERROR)
        self._streamHandler = logging.StreamHandler()
        self._formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self._streamHandler.setFormatter(self._formatter)
        self._logger.addHandler(self._streamHandler)

    @classmethod
    def discovery_completed(self):
        """Discovery completed.

        Returns:
            bool: True if the discovery process has completed, False otherwise.
        """ 
        return AWSGreengrass._discovery_completed

    def get_client(self, client_id, device_certificate_path, device_private_key_path):
        """Get an Amazon AWS client.

        Args:
            client_id (str): Name of the client, as it is on the cloud.
            device_certificate_path (str): Relative path of the device's
                certificate stored on the core device.
            device_private_key_path (str): Relative path of the device's
                private key stored on the core device.

        Returns:
            :class:`edge_st_sdk.aws.aws_client.AWSClient`: Amazon AWS client.
        """
        # Performing the discovery of the core belonging to the same group of
        # the client.
        if not self._discovery_completed:
            self._discover_core(client_id, device_certificate_path, device_private_key_path)

        # Creating the client.
        return edge_st_sdk.aws.aws_client.AWSClient(client_id, device_certificate_path, device_private_key_path, self._group_ca_path, self._core_info)
