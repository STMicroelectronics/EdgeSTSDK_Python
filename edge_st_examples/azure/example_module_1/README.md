
This Example used 2 BLE devices and toggles the switch from one device to another.
The BLE device 1 (MAC_ADDR_1) sends the toggle switch message to the BLE device 2 (MAC_ADDR_2).
The Blue button on the Nucleo serves as the switch button.
Pressing the Blue button on BLE device 1 will send the switch message to the other device.
In effect the LED on the BLE Device 2 Nucleo should toggle on pressing of above button.
Pressing the Blue button on BLE device 2 does not yield any result in this example.

Input (while adding module) the following env variables with MAC addresses of relevant BLE devices:
'MAC_ADDR_1'
'MAC_ADDR_2'

If not entered as env variables, the MAC addresses will be default addresses as hardcoded in example.

A built container of this module should already be available at the following location:
stmedge.azurecr.io/mod-edgestsdk-example:0.0.2-arm32v7

Access to above container will require container registry access keys.