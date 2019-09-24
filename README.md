# EdgeST SDK

EdgeST SDK is an IoT edge computing abstraction library for Linux gateways. It relies on cloud platforms' edge SDKs to enable local execution of functions on a Linux gateway and synchronization to the cloud.

More specifically, it enables the creation of "virtual" devices on the gateway that map to non-IP connected devices (e.g. via Bluetooth Low Energy technology), and the corresponding "shadow" devices on the cloud. Local computation can be performed directly on the gateway with the same logic written for the cloud even when Internet connection is lost, and shadow devices will be synchronized to virtual devices as soon as Internet connection becomes available.

Currently [Amazon AWS Greengrass](https://aws.amazon.com/it/greengrass/) edge computing service is supported, while other cloud engines will be added in the future.


## Documentation
Documentation can be found [here](https://stmicroelectronics.github.io/EdgeSTSDK_Python/index.html).


## Compatibility
This version of the SDK is compatible with [Python](https://www.python.org/) 3.5 and runs on a Linux system.


## Preconditions
The SDK relies on the Amazon AWS Greengrass SDK, so please refer to the [Amazon AWS Greengrass official documentation](https://docs.aws.amazon.com/greengrass/latest/developerguide/what-is-gg.html) to install it. At the time of writing, this implies installing the following components:
1. Amazon AWS IoT Python SDK:
```Shell
$ sudo pip3 install AWSIoTPythonSDK
```
2. Amazon AWS IoT Greengrass SDK, that will be downloaded when creating a "Group" on the AWS web IoT Console on the cloud. Further actions are required to setup the environment, so please follow the abovementioned official documentation.
Moreover, please install the [concurrent.futures](https://docs.python.org/3/library/concurrent.futures.html) module to run pools of threads in background, that serve listeners' callbacks.
```Shell
$ sudo pip3 install futures
```
Last but not least, the Python version of the [BlueST SDK](https://github.com/STMicroelectronics/EdgeSTSDK_Python#bluest-sdk) is required to run the provided application examples.


## Installation
The EdgeST SDK can be installed through the Python pip package manager.
```Shell
$ sudo pip3 install edge-st-sdk
```


## BlueST SDK
BlueST SDK is a multi-platform library available for [Linux](https://github.com/STMicroelectronics/BlueSTSDK_Python) (beyond [Android](https://github.com/STMicroelectronics/BlueSTSDK_Android) and [iOS](https://github.com/STMicroelectronics/BlueSTSDK_iOS)) that allows easy access to the data exported by a Bluetooth Low Energy (BLE) device that implements the [BlueST Protocol](https://github.com/STMicroelectronics/BlueSTSDK_Python#bluest-protocol).

The Linux version of the SDK, written in Python, is needed to let BLE devices connect to a Linux gateway. This enables IoT applications where BLE connected devices stream data to a gateway through the BlueST SDK, while the EdgeST SDK abstracts edge computing operations performed locally on the gateway and the synchronization to the shadow devices on the cloud.


## Setting up the application examples
Before running the application examples, please prepare your devices as described here below:
* The [example_ble_aws_1.py](https://github.com/STMicroelectronics/EdgeSTSDK_Python/blob/master/edge_st_examples/aws/example_ble_aws_1.py) and the [example_ble_aws_2.py](https://github.com/STMicroelectronics/EdgeSTSDK_Python/blob/master/edge_st_examples/aws/example_ble_aws_2.py) application examples show how to handle two BLE devices implementing the [BlueST Protocol](https://github.com/STMicroelectronics/BlueSTSDK_Python#bluest-protocol) that connect to a Linux gateway, and to make them communicate to the Amazon AWS IoT Cloud through the AWS Greengrass edge computing service. The former shows a usage of the "Switch" feature in such a way that pressing the user button on a device makes the LED of the other device toggle its status through a logic defined by the [GG_Switch_Lambda.py](https://github.com/STMicroelectronics/EdgeSTSDK_Python/blob/master/edge_st_examples/aws/GG_Switch_Lambda.py) lambda function. The latter adds the handling of environmental and inertial features so that data from Pressure, Humidity, Temperature, Accelerometer, Gyroscope, and Magnetometer sensors are sent to the IoT Cloud.

The applications require to set up two devices equipped with BLE connectivity, e.g.:
* Two [NUCLEO-F401RE](http://www.st.com/content/st_com/en/products/evaluation-tools/product-evaluation-tools/mcu-eval-tools/stm32-mcu-eval-tools/stm32-mcu-nucleo/nucleo-f401re.html) development boards
* Two [X-NUCLEO-IDB05A1](http://www.st.com/content/st_com/en/products/ecosystems/stm32-open-development-environment/stm32-nucleo-expansion-boards/stm32-ode-connect-hw/x-nucleo-idb05a1.html) Bluetooth Low Energy expansion boards
* Import the [Node_BLE_Switch_Device](https://os.mbed.com/teams/ST/code/Node_BLE_Switch_Device/) or the [Node_BLE_Sensors_Device](https://os.mbed.com/teams/ST/code/Node_BLE_Sensors_Device/) mbed OS application to your ARM mbed account respectively for the first or the second application example, compile, and flash it onto the MCU board
* Edit the application example and set the "IOT_DEVICE_X_NAME" and "IOT_DEVICE_X_MAC" global variables properly (you can use a smartphone application to retrieve the MAC address)
* Put the certificates and the private keys of your devices into the folder on the Linux gateway specified by the "DEVICES_PATH" global variable
* Follow carefully the instructions described within the [Examples_ble_aws.pdf](https://github.com/STMicroelectronics/EdgeSTSDK_Python/blob/master/edge_st_examples/aws/Examples_ble_aws.pdf) application manual to configure the application on the cloud.


## Running the application examples
To run the application examples please follow the steps below:
1. Install the EdgeST SDK as described by the [Installation](https://github.com/STMicroelectronics/EdgeSTSDK_Python#installation) chapter.
2. Install the BlueST SDK as described by the [Installation](https://github.com/STMicroelectronics/BlueSTSDK_Python#installation) chapter.
3. Clone the EdgeST SDK git repository to download the application examples:
```Shell
$ git clone https://github.com/STMicroelectronics/EdgeSTSDK_Python.git
```
4. Start the Greengrass daemon:
```Shell
$ sudo /greengrass/ggc/core/greengrassd restart
```
5. Enter the "edge_st_examples" folder and run the desired script by providing the endpoint (i.e. IoT host) and the path of the root Certification Authority certificate. You can find these information within the "config.json" configuration file that comes from Amazon AWS when creating a Greengrass group (please refer to the [Amazon AWS Greengrass official documentation](https://docs.aws.amazon.com/greengrass/latest/developerguide/what-is-gg.html)), e.g.:
```Shell
$ sudo python3 example_ble_aws_x.py -e <iot_host_prefix>.iot.<region>.amazonaws.com -r /greengrass/certs/root.ca.pem
```


## License
COPYRIGHT(c) 2019 STMicroelectronics

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
1. Redistributions of source code must retain the above copyright notice,
this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above 
notice, this list of conditions and the following disclaimer in the
documentation and/or other materials provided with the distribution.
3. Neither the name of STMicroelectronics nor the names of its
contributors may be used to endorse or promote products derived from
this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
