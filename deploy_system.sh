#!/bin/bash

# Real-Time IoT System Deployment Script
# Complete system deployment with simulated nodes and web monitoring

set -e

PROJECT_ROOT="/home/herocod/Documents/UniPi/IOT/IotProject"
WEBAPP_DIR="$PROJECT_ROOT/webapp"
LOG_DIR="$PROJECT_ROOT/logs"

echo "🚀 Starting Real-Time IoT Energy Monitoring System Deployment"
echo "=============================================================="

# Create log directory
mkdir -p "$LOG_DIR"

# Test system connectivity first
echo "🔍 Testing system connectivity..."
cd "$PROJECT_ROOT"
if python3 test_connections.py; then
    echo "✅ All connections successful!"
else
    echo "⚠️  Some connections failed, but continuing deployment..."
    echo "   You may need to start services manually:"
    echo "   - sudo systemctl start mysql"
    echo "   - sudo systemctl start mosquitto"
fi
echo

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to start service in background with logging
start_service() {
    local name="$1"
    local command="$2"
    local log_file="$LOG_DIR/${name}.log"
    
    echo "📦 Starting $name..."
    nohup bash -c "$command" > "$log_file" 2>&1 &
    local pid=$!
    echo $pid > "$LOG_DIR/${name}.pid"
    echo "   ✅ $name started (PID: $pid, Log: $log_file)"
}

# Function to stop service
stop_service() {
    local name="$1"
    local pid_file="$LOG_DIR/${name}.pid"
    
    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo "🛑 Stopping $name (PID: $pid)..."
            kill "$pid"
            rm -f "$pid_file"
        else
            echo "   ⚠️  $name process not running"
            rm -f "$pid_file"
        fi
    else
        echo "   ⚠️  No PID file found for $name"
    fi
}

# Function to check service status
check_service() {
    local name="$1"
    local pid_file="$LOG_DIR/${name}.pid"
    
    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo "   ✅ $name is running (PID: $pid)"
            return 0
        else
            echo "   ❌ $name is not running"
            rm -f "$pid_file"
            return 1
        fi
    else
        echo "   ❌ $name is not running"
        return 1
    fi
}

# Parse command line arguments
ACTION="${1:-start}"

case "$ACTION" in
    "start")
        echo "🔧 Starting all services..."
        
        # Check dependencies
        echo "🔍 Checking dependencies..."
        
        if ! command_exists docker; then
            echo "❌ Docker not found. Please install Docker first."
            exit 1
        fi
        
        if ! command_exists python3; then
            echo "❌ Python 3 not found. Please install Python 3 first."
            exit 1
        fi
        
        echo "   ✅ All dependencies found"
        
        # Start Docker services (MQTT broker and MySQL)
        echo "🐳 Starting Docker services..."
        cd "$PROJECT_ROOT"
        docker compose up -d
        echo "   ✅ Docker services started"
        
        # Wait for services to be ready
        echo "⏳ Waiting for services to initialize..."
        sleep 10
        
        # Install webapp dependencies
        echo "📦 Installing webapp dependencies..."
        cd "$WEBAPP_DIR"
        if [[ ! -d "venv" ]]; then
            python3 -m venv venv
        fi
        source venv/bin/activate
        pip install -r requirements.txt
        echo "   ✅ Webapp dependencies installed"
        
        # Start data collector service
        start_service "collector" "cd '$PROJECT_ROOT' && python3 collector/collector.py"
        
        # Start Flask webapp
        start_service "webapp" "cd '$WEBAPP_DIR' && source venv/bin/activate && python3 app.py --host 0.0.0.0 --port 5000"
        
        # Start simulated IoT nodes (if Cooja not available)
        start_service "node1_sim" "cd '$PROJECT_ROOT' && python3 -c \"
import time
import json
import paho.mqtt.publish as publish
import random
from datetime import datetime

mqtt_broker = 'localhost'
device_id = 'node1'

print('🏠 Starting Node 1 (Living Room) Simulator')

button_count = 0
manual_override = 0
led_status = 0

while True:
    # Simulate realistic sensor data
    data = {
        'device_id': device_id,
        'location': 'living_room',
        'lux': 30 + random.randint(0, 60),
        'occupancy': random.choice([0, 0, 1, 1, 1]),  # 60% occupied
        'temperature': 20 + random.randint(0, 10),
        'room_usage': round(random.uniform(0.05, 0.20), 3),
        'led_status': led_status,
        'manual_override': manual_override,
        'energy_saving_mode': random.choice([0, 1]),
        'button_presses': button_count
    }
    
    # Occasionally simulate button press
    if random.randint(1, 100) <= 5:  # 5% chance
        button_count += 1
        manual_override = 1 - manual_override
        print(f'🔘 Button pressed! Manual override: {manual_override}')
    
    topic = 'sensors/node1/data'
    publish.single(topic, json.dumps(data), hostname=mqtt_broker)
    print(f'📊 {device_id}: Lux={data[\"lux\"]}, Occ={data[\"occupancy\"]}, Usage={data[\"room_usage\"]}kWh')
    
    time.sleep(10)
\""
        
        start_service "node2_sim" "cd '$PROJECT_ROOT' && python3 -c \"
import time
import json
import paho.mqtt.publish as publish
import random

mqtt_broker = 'localhost'
device_id = 'node2'

print('🏠 Starting Node 2 (Kitchen) Simulator')

button_count = 0
manual_override = 0
led_status = 0

while True:
    data = {
        'device_id': device_id,
        'location': 'kitchen',
        'lux': 40 + random.randint(0, 50),
        'occupancy': random.choice([0, 1, 1, 1]),  # 75% occupied
        'temperature': 22 + random.randint(0, 8),
        'room_usage': round(random.uniform(0.08, 0.30), 3),  # Higher kitchen usage
        'led_status': led_status,
        'manual_override': manual_override,
        'energy_saving_mode': random.choice([0, 1]),
        'button_presses': button_count
    }
    
    if random.randint(1, 100) <= 3:  # 3% chance
        button_count += 1
        manual_override = 1 - manual_override
        print(f'🔘 Button pressed! Manual override: {manual_override}')
    
    topic = 'sensors/node2/data'
    publish.single(topic, json.dumps(data), hostname=mqtt_broker)
    print(f'📊 {device_id}: Lux={data[\"lux\"]}, Occ={data[\"occupancy\"]}, Usage={data[\"room_usage\"]}kWh')
    
    time.sleep(10)
\""
        
        start_service "node3_sim" "cd '$PROJECT_ROOT' && python3 -c \"
import time
import json
import paho.mqtt.publish as publish
import random

mqtt_broker = 'localhost'
device_id = 'node3'

print('🏠 Starting Node 3 (Bedroom) Simulator')

button_count = 0
manual_override = 0
led_status = 0

while True:
    data = {
        'device_id': device_id,
        'location': 'bedroom',
        'lux': 15 + random.randint(0, 45),  # Dimmer bedroom
        'occupancy': random.choice([0, 0, 1, 1]),  # 50% occupied (sleep cycles)
        'temperature': 18 + random.randint(0, 8),
        'room_usage': round(random.uniform(0.02, 0.15), 3),  # Lower bedroom usage
        'led_status': led_status,
        'manual_override': manual_override,
        'energy_saving_mode': random.choice([0, 1]),
        'button_presses': button_count
    }
    
    if random.randint(1, 100) <= 4:  # 4% chance
        button_count += 1
        manual_override = 1 - manual_override
        print(f'🔘 Button pressed! Manual override: {manual_override}')
    
    topic = 'sensors/node3/data'
    publish.single(topic, json.dumps(data), hostname=mqtt_broker)
    print(f'📊 {device_id}: Lux={data[\"lux\"]}, Occ={data[\"occupancy\"]}, Usage={data[\"room_usage\"]}kWh')
    
    time.sleep(10)
\""
        
        echo ""
        echo "🎉 System deployment complete!"
        echo "=============================================================="
        echo "📊 Web Dashboard: http://localhost:5000"
        echo "🎮 Device Control: http://localhost:5000/control"
        echo "📈 Analytics: http://localhost:5000/analytics"
        echo "📡 MQTT Broker: localhost:1883"
        echo "🗄️  MySQL Database: localhost:3306"
        echo ""
        echo "📋 Service Status:"
        check_service "collector"
        check_service "webapp"
        check_service "node1_sim"
        check_service "node2_sim"
        check_service "node3_sim"
        echo ""
        echo "📝 Logs available in: $LOG_DIR"
        echo "🛑 To stop all services: $0 stop"
        ;;
        
    "stop")
        echo "🛑 Stopping all services..."
        
        # Stop Python services
        stop_service "node3_sim"
        stop_service "node2_sim"
        stop_service "node1_sim"
        stop_service "webapp"
        stop_service "collector"
        
        # Stop Docker services
        echo "🐳 Stopping Docker services..."
        cd "$PROJECT_ROOT"
        docker compose down
        echo "   ✅ Docker services stopped"
        
        echo "✅ All services stopped"
        ;;
        
    "status")
        echo "📋 Service Status:"
        echo "=================="
        
        # Check Docker services
        echo "🐳 Docker Services:"
        cd "$PROJECT_ROOT"
        docker compose ps
        echo ""
        
        # Check Python services
        echo "🐍 Python Services:"
        check_service "collector"
        check_service "webapp"
        check_service "node1_sim"
        check_service "node2_sim"
        check_service "node3_sim"
        echo ""
        
        echo "📊 Web Dashboard: http://localhost:5000"
        ;;
        
    "logs")
        SERVICE="${2:-all}"
        
        if [[ "$SERVICE" == "all" ]]; then
            echo "📝 Showing all service logs (last 50 lines each):"
            echo "================================================="
            
            for log_file in "$LOG_DIR"/*.log; do
                if [[ -f "$log_file" ]]; then
                    echo ""
                    echo "--- $(basename "$log_file" .log) ---"
                    tail -n 50 "$log_file"
                fi
            done
        else
            log_file="$LOG_DIR/${SERVICE}.log"
            if [[ -f "$log_file" ]]; then
                echo "📝 Showing logs for $SERVICE:"
                tail -f "$log_file"
            else
                echo "❌ Log file not found for service: $SERVICE"
                echo "Available services: collector, webapp, node1_sim, node2_sim, node3_sim"
            fi
        fi
        ;;
        
    "restart")
        echo "🔄 Restarting system..."
        "$0" stop
        sleep 5
        "$0" start
        ;;
        
    *)
        echo "Usage: $0 {start|stop|status|logs [service]|restart}"
        echo ""
        echo "Commands:"
        echo "  start    - Start all services (MQTT, MySQL, collector, webapp, simulated nodes)"
        echo "  stop     - Stop all services"
        echo "  status   - Show status of all services"
        echo "  logs     - Show logs (use 'logs [service]' for specific service)"
        echo "  restart  - Restart all services"
        echo ""
        echo "Example: $0 logs webapp"
        exit 1
        ;;
esac
