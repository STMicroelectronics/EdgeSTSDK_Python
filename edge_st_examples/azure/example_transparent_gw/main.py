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


import random
import time
import sys
import os
import json
import requests
import threading
import asyncio
import uuid
from six.moves import input
from datetime import datetime, tzinfo, timedelta
import concurrent
# pylint: disable=E0611
from enum import Enum
from edge_st_sdk.azure.azure_client import AzureClient
from edge_st_sdk.utils.edge_st_exceptions import EdgeSTInvalidOperationException, EdgeSTInvalidDataException


class simple_utc(tzinfo):
    def tzname(self,**kwargs):
        return "UTC"
    def utcoffset(self, dt):
        return timedelta(0)

MODULE_NAME = os.getenv('MODULE_NAME','tpgwmod')
MODULEID = os.environ["IOTEDGE_MODULEID"]
DEVICEID = os.environ["IOTEDGE_DEVICEID"]

# INTERFACES

# define behavior for receiving direct method requests
async def method_request_listener(module_client):
    while True:
        print("waiting for method request...")
        method_request = await module_client.get_method_request(None)
        print(method_request) 
        print(method_request.payload) #type: dict
        status = 200
        payload = "{\"result\":\"success\"}"        
        await module_client.send_method_response(method_request, payload, status)
        print("sent method response")
            

# Define behavior for receiving an input message on input1
# Because this is a filter module, we forward this message to the "output1" queue.
async def input1_listener(module_client):
    while True:
        try:
            print("listening...")
            input_message = await module_client.subscribe("input1")  # blocking call
            message = input_message.data
            size = len(message)
            message_text = message.decode('utf-8')
            print ( "    Data: <<<%s>>> & Size=%d" % (message_text, size) )
            custom_properties = input_message.custom_properties
            print ( "    Properties: %s" % custom_properties )            
        except Exception as ex:
            print ( "Unexpected error in input1_listener: %s" % ex )


# twin_patch_listener is invoked when the module twin's desired properties are updated.
async def twin_patch_listener(module_client):
    while True:
        try:
            data = await module_client.get_shadow_state(None, 0)  # blocking call
            print( "The data in the desired properties patch was: %s" % data)
        except Exception as ex:
            print ( "Unexpected error in twin_patch_listener: %s" % ex )


def wait_for_dev_notifications():

    print("Thread: Wait for notifications...")
    while True:
        print(">>>>>")
        time.sleep(10)


async def main():   

    try:
        if not sys.version >= "3.5.3":
            raise Exception( "The sample requires python 3.5.3+. Current version of Python: %s" % sys.version )
        print ( "\nSTM32MP1 module EW2020\n")
        print ( "\nPython %s\n" % sys.version )
        
        # initialize_client
        module_client = AzureClient(MODULE_NAME)

        # Connecting clients to the runtime.
        print("going to connect to ModuleClient....")
        await module_client.connect()
        print("module connected to [%s]: [%s]..."% (MODULE_NAME, MODULEID))

        def stdin_listener():
            while True:
                try:
                    selection = input("Press Q to quit\n")
                    if selection == "Q" or selection == "q":
                        print("Quitting...")
                        break
                except:
                    time.sleep(5)

        loop = asyncio.get_event_loop()

        # Schedule task for listeners
        listeners = asyncio.gather(input1_listener(module_client), method_request_listener(module_client))
        
        # Start thread to handle notifications
        notifications_task = threading.Thread(target=wait_for_dev_notifications)
        notifications_task.start()

        # Run the ble synchronous handler in the event loop
        user_finished = loop.run_in_executor(None, stdin_listener)
        await user_finished
        print("finished waiting for user input")

        # Cancel listening
        listeners.cancel()
        # Stop thread
        notifications_task.join()

        # Finally, disconnect
        await module_client.disconnect()                           

    except KeyboardInterrupt:
        print ( "IoTHubModuleClient sample stopped" )

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()

    # asyncio.run(main())
