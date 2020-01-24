This example is the module for the Embedded World Demo 2020

This example uses a BLE device (User can specify MAC_ADDR as env var) through the blueSTSDK-Python API.
This example is a Azure IoTEdge module and this module can be used to do the following:

1. Upgrade the FW in the BLE node through the ST Dashboard. Currently supports update of the binaries included in the bin image. Support of more binary images needs to be adapted in the source code.
2. Send AI event reports to the IoTHub and the ST Dashboard

Please build the docker container using the script docker-build.sh
Please make sure to change the container image name from the default.
The default image stmedge.azurecr.io/modaievt_tpgw:0.0.1-arm32v7 access needs appropriate access keys for login and pushing.
 
