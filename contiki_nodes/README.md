# IoT Nodes Simulation

We provide 3 nodes (node1, node2, node3):

- Each publishes simulated “light sensor” values every 10s.
- Each subscribes to `actuators/nodeX/led` for commands.
- Toggling LED simulates turning ON/OFF a real light on the nRF52840 board.

## Build

cd contiki_nodes
make node1.node
make node2.node
make node3.node TARGET=nrf52840

## Simulate in Cooja

- Open Cooja
- Add 3 nodes (`node1`, `node2`, `node3`)
- Add border router
- Configure broker connection: MQTT_BROKER_IP should match NAT’d address of Docker Mosquitto (`fd00::1` in Cooja simulation)
