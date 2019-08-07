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
from abc import ABCMeta
from abc import abstractmethod
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

from AWSIoTPythonSDK.core.greengrass.discovery.providers import DiscoveryInfoProvider
from AWSIoTPythonSDK.core.protocol.connection.cores import ProgressiveBackOffCore
from AWSIoTPythonSDK.exception.AWSIoTExceptions import DiscoveryInvalidRequestException

from edge_st_sdk.utils.python_utils import lock
import edge_st_sdk.aws.aws_client
from edge_st_sdk.utils.edge_st_exceptions import EdgeSTInvalidOperationException
from edge_st_sdk.utils.edge_st_exceptions import EdgeSTInvalidDataException


# CLASSES

class AWSGreengrass(object):

    MAX_DISCOVERY_ATTEMPTS = 3
    """Maximum number of attempts when trying to discover the core."""

    _GROUP_CA_PATH  = './aws_group_ca/'
    """Group Certification Authority path.""" 

    _TIMEOUT_s = 10
    """Timeout for discovering information."""

    _NUMBER_OF_THREADS = 5
    """Number of threads to be used to notify the listeners."""

    _discovery_completed = False
    """Discovery completed flag."""

    def __init__(self, endpoint, root_ca_path):
        """Constructor.

        Initializing AWS Discovery.

        :param endpoint: AWS endpoint.
        :type endpoint: str

        :param root_ca_path: Path to the root Certification Authority file.
        :type root_ca_path: str
        """
        self._status = AWSGreengrassStatus.INIT
        """Status."""

        self._thread_pool = ThreadPoolExecutor(AWSGreengrass._NUMBER_OF_THREADS)
        """Pool of thread used to notify the listeners."""

        self._listeners = []
        """List of listeners to the feature changes.
        It is a thread safe list, so a listener can subscribe itself through a
        callback."""

        self._endpoint = endpoint
        """AWS endpoint."""

        self._root_ca_path = root_ca_path
        """Path to the root Certification Authority file."""

        self._group_ca_path = None
        """Path to the group Certification Authority file."""

        self._core_info = None
        """Core information."""

        # Updating service.
        self._update_status(AWSGreengrassStatus.IDLE)

    def _discover_core(self, client_id, device_certificate_path,
        device_private_key_path):
        """Performing the discovery of the core belonging to the same group of
        the given client name.

        :param client_id: Name of a client, as it is on the cloud, belonging
            to the same group of the core.
        :type client_id: str

        :param device_certificate_path: Relative path of a device's
            certificate stored on the core device, belonging to the same group
            of the core.
        :type device_certificate_path: str

        :param device_private_key_path: Relative path of a device's
            private key stored on the core device, belonging to the same group
            of the core.
        :type device_private_key_path: str

        :returns: The name of the core.
        :rtype: str

        :raises EdgeSTInvalidOperationException: is raised if the discovery of
            the core fails.
        :raises EdgeSTInvalidDataException: is raised a wrong configuration data
            is provided.
        """

        # Checking configuration parameters.
        if not os.access(self._root_ca_path, os.R_OK):
            msg = '\nRoot Certification Authority certificate path "%s" is not ' \
                'accessible.\r\n' \
                'Please run the application with \"sudo\".' \
                % (device_certificate_path)
            raise EdgeSTInvalidDataException(msg)
        if not os.path.exists(device_certificate_path):
            msg = '\nInvalid device certificate path: "%s"' \
            % (device_certificate_path)
            raise EdgeSTInvalidDataException(msg)
        if not os.path.exists(device_private_key_path):
            msg = '\nInvalid device private key path: "%s"' \
            % (device_private_key_path)
            raise EdgeSTInvalidDataException(msg)

        # Updating service.
        self._update_status(AWSGreengrassStatus.DISCOVERING_CORE)

        # Progressive back off core.
        backOffCore = ProgressiveBackOffCore()

        # Discover GGCs.
        discoveryInfoProvider = DiscoveryInfoProvider()
        discoveryInfoProvider.configureEndpoint(self._endpoint)
        discoveryInfoProvider.configureCredentials(
            self._root_ca_path,
            device_certificate_path,
            device_private_key_path)
        discoveryInfoProvider.configureTimeout(self._TIMEOUT_s)
        attempts = AWSGreengrass.MAX_DISCOVERY_ATTEMPTS

        while attempts != 0:
            try:
                # Discovering information.
                discoveryInfo = discoveryInfoProvider.discover(client_id)
                caList = discoveryInfo.getAllCas()
                coreList = discoveryInfo.getAllCores()

                # Picking only the first ca and core info.
                group_id, ca = caList[0]
                self._core_info = coreList[0]

                # Persisting connectivity/identity information.
                self._group_ca_path = self._GROUP_CA_PATH + group_id + \
                    '_CA_' + str(uuid.uuid4()) + '.crt'
                if not os.path.exists(self._GROUP_CA_PATH):
                    os.makedirs(self._GROUP_CA_PATH)
                group_ca_path_file = open(self._group_ca_path, 'w')
                group_ca_path_file.write(ca)
                group_ca_path_file.close()
                break

            except DiscoveryInvalidRequestException as e:
                raise EdgeSTInvalidOperationException(
                    'Invalid discovery request detected: %s' % (e.message))

            except BaseException as e:
                attempts -= 1
                backOffCore.backOff()
                if attempts == 0:
                    raise EdgeSTInvalidOperationException(
                        'Discovery of the core related to the client "%s", with ' \
                        'certificate "%s" and key "%s", failed after %d retries.' % \
                        (client_id,
                         device_certificate_path,
                         device_private_key_path,
                         AWSGreengrass.MAX_DISCOVERY_ATTEMPTS))

        self._configure_logging()
        AWSGreengrass._discovery_completed = True

        # Updating service.
        self._update_status(AWSGreengrassStatus.CORE_DISCOVERED)

        return self._core_info.coreThingArn

    def _configure_logging(self):
        """Configuring logging, required for using shadow devices."""
        self._logger = logging.getLogger('AWSIoTPythonSDK.core')
        self._logger.setLevel(logging.ERROR)
        self._streamHandler = logging.StreamHandler()
        self._formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self._streamHandler.setFormatter(self._formatter)
        self._logger.addHandler(self._streamHandler)

    @classmethod
    def discovery_completed(self):
        """Checking whether the discovery has completed.

        :returns: True if the discovery process has completed, False otherwise.
        :rtype: bool
        """ 
        return AWSGreengrass._discovery_completed

    def get_client(self, client_id, device_certificate_path,
        device_private_key_path):
        """Getting an Amazon AWS client.

        :param client_id: Name of the client, as it is on the cloud.
        :type client_id: str

        :param device_certificate_path: Relative path of a device's
            certificate stored on the core device.
        :type device_certificate_path: str

        :param device_private_key_path: Relative path of a device's
            private key stored on the core device.
        :type device_private_key_path: str

        :returns: Amazon AWS client.
        :rtype: :class:`edge_st_sdk.aws.aws_client.AWSClient`

        :raises EdgeSTInvalidOperationException: is raised if the discovery of
            the core fails.
        :raises EdgeSTInvalidDataException: is raised if a wrong configuration
            data is provided.
        """
        # Performing the discovery of the core belonging to the same group of
        # the client.
        try:
            if not self.discovery_completed():
                self._discover_core(
                    client_id,
                    device_certificate_path,
                    device_private_key_path)

            # Creating the client.
            return edge_st_sdk.aws.aws_client.AWSClient(
                client_id,
                device_certificate_path,
                device_private_key_path,
                self._group_ca_path,
                self._core_info)

        except (EdgeSTInvalidDataException, EdgeSTInvalidOperationException) \
            as e:
            raise e

    def get_endpoint(self):
        """Getting the AWS endpoint."""
        return self._endpoint

    def add_listener(self, listener):
        """Add a listener.
        
        :param listener: Listener to be added.
        :type listener: :class:`edge_st_sdk.aws.aws_greengrass.AWSGreengrassListener`
        """
        if listener is not None:
            with lock(self):
                if not listener in self._listeners:
                    self._listeners.append(listener)

    def remove_listener(self, listener):
        """Remove a listener.

        :param listener: Listener to be removed.
        :type listener: :class:`edge_st_sdk.aws.aws_greengrass.AWSGreengrassListener`
        """
        if listener is not None:
            with lock(self):
                if listener in self._listeners:
                    self._listeners.remove(listener)

    def _update_status(self, new_status):
        """Update the status of the client.

        :param new_status: New status.
        :type new_status: :class:`edge_st_sdk.aws.aws_greengrass.AWSGreengrassStatus`
        """
        old_status = self._status
        self._status = new_status
        for listener in self._listeners:
            # Calling user-defined callback.
            self._thread_pool.submit(
                listener.on_status_change(
                    self, new_status.value, old_status.value))


class AWSGreengrassStatus(Enum):
    """Status of the AWS Greengrass service."""

    INIT = 'INIT'
    """Dummy initial status."""

    IDLE = 'IDLE'
    """Waiting for a connection and sending advertising data."""

    DISCOVERING_CORE = 'DISCOVERING_CORE'
    """Discovering the Core."""

    CORE_DISCOVERED = 'CORE_DISCOVERED'
    """Core discovered."""


# INTERFACES

class AWSGreengrassListener(object):
    """Interface used by the
    :class:`edge_st_sdk.aws.aws_greengrass.AWSGreengrass` class to notify
    changes of an AWS Greengrass service's status.
    """
    __metaclass__ = ABCMeta

    @abstractmethod
    def on_status_change(self, aws_greengrass, new_status, old_status):
        """To be called whenever the AWS Greengrass service changes its status.

        :param aws_greengrass: AWS Greengrass service that has changed its
            status.
        :type aws_greengrass: :class:`edge_st_sdk.aws.aws_greengrass.AWSGreengrass`

        :param new_status: New status.
        :type new_status: :class:`edge_st_sdk.aws.aws_greengrass.AWSGreengrassStatus`

        :param old_status: Old status.
        :type old_status: :class:`edge_st_sdk.aws.aws_greengrass.AWSGreengrassStatus`

        :raises NotImplementedError: if the method has not been implemented.
        """
        raise NotImplementedError('You must implement "on_status_change()" to '
                                  'use the "AWSGreengrassListener" class.')
