#!/bin/bash

# Wait for MQTT broker to be ready
echo "🔌 Waiting for MQTT broker to be ready..."
while ! nc -z mosquitto 1883; do
    echo "⏳ Waiting for MQTT broker..."
    sleep 2
done

echo "✅ MQTT broker is ready"

# Wait for controller to be ready
echo "🔌 Waiting for controller to be ready..."
while ! nc -z controller 5001; do
    echo "⏳ Waiting for controller..."
    sleep 2
done

echo "✅ Controller is ready"

# Start virtual nodes
echo "🎭 Starting Virtual IoT Nodes..."
python virtual_nodes.py
