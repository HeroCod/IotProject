#!/bin/bash
# IoT Project - Unified Management Script
# 
# Cloud-ready IoT Energy Management System
# Controller backend + Web frontend architecture
#
# Usage:
#   ./run.sh init         -> Initialize project and install dependencies
#   ./run.sh start        -> Start complete system (Docker + simulated nodes)
#   ./run.sh start --virtual -> Start complete system with virtual nodes
#   ./run.sh stop         -> Stop all services
#   ./run.sh sim          -> Start with Cooja simulation
#   ./run.sh build        -> Build Docker containers
#   ./run.sh logs         -> Show logs
#   ./run.sh cli <cmd>    -> CLI commands (bonus)

PROJECT_DIR=$(pwd)
LOG_DIR="$PROJECT_DIR/logs"

# Ensure logs directory exists
mkdir -p "$LOG_DIR"

case "$1" in
  init)
    echo "🚀 Initializing IoT Energy Management System..."
    echo "================================================"
    
    echo "📦 Installing system dependencies..."
    sudo apt-get update
    sudo apt-get install -y git ant ca-certificates curl python3 python3-pip
    
    echo "🐳 Installing Docker..."
    # Install Docker if not present
    if ! command -v docker &> /dev/null; then
        sudo install -m 0755 -d /etc/apt/keyrings
        sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
        sudo chmod a+r /etc/apt/keyrings/docker.asc
        
        echo \
            "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
            $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
            sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        
        sudo apt-get update
        sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        sudo usermod -aG docker $USER
        
        echo "⚠️  Please log out and back in for Docker permissions to take effect"
    fi
    
    echo "🔧 Initializing Contiki-NG..."
    if [ ! -d "contiki-ng/tools" ]; then
      git clone --recurse-submodules https://github.com/contiki-ng/contiki-ng.git ./contiki-ng
    fi
    
    echo "✅ Initialization complete!"
    echo "💡 Next steps:"
    echo "   1. Log out and back in (for Docker permissions)"
    echo "   2. Run: ./run.sh start"
    ;;

  build)
    echo "🔨 Building IoT system containers..."
    docker compose build
    echo "✅ Build complete!"
    ;;

  start)
    # Check for --virtual argument
    if [ "$2" = "--virtual" ]; then
        echo "🚀 Starting Complete IoT Energy Management System with Virtual Nodes..."
        echo "====================================================================="
    else
        echo "🚀 Starting Complete IoT Energy Management System..."
        echo "=================================================="
    fi
    
    # Build containers if needed
    if ! docker images | grep -q iot_controller; then
        echo "📦 Building containers..."
        docker compose build
    fi
    
    # Start core services
    echo "🌐 Starting core services (MySQL, MQTT, Controller, WebApp)..."
    docker compose up -d
    
    # Wait for services to be ready
    echo "⏳ Waiting for services to start..."
    sleep 10
    
    # Start simulated IoT nodes only if --virtual flag is used or if it's the default behavior
    if [ "$2" = "--virtual" ] || [ -z "$2" ]; then
        echo "🎭 Starting virtual IoT nodes..."
        $0 start-simulators
    else
        echo "ℹ️  Virtual nodes not started. Use --virtual flag to include them."
    fi
    
    echo "✅ System started successfully!"
    echo ""
    echo "🌍 Access points:"
    echo "   📊 Web Dashboard:    http://localhost:5000"
    echo "   🎛️  Device Control:   http://localhost:5000/control"
    echo "   📈 Analytics:        http://localhost:5000/analytics"
    echo "   🔧 Controller API:   http://localhost:5001/api/status"
    echo ""
    echo "📋 System status:"
    echo "   MQTT Broker:    localhost:1883"
    echo "   MySQL DB:       localhost:3306"
    echo "   Controller:     localhost:5001"
    echo "   WebApp:         localhost:5000"
    echo ""
    echo "📝 View logs with: ./run.sh logs"
    ;;

  start-simulators)
    echo "🎭 Starting interactive virtual IoT nodes..."
    
    # Kill any existing simulators
    pkill -f "python.*virtual_nodes" 2>/dev/null || true
    
    # Check if virtual_nodes.py exists
    if [ ! -f "virtual_nodes.py" ]; then
        echo "❌ No simulator found!"
        return 1
    fi
    
    # Start the new interactive virtual nodes
    echo "🚀 Starting interactive virtual nodes system..."
    nohup python3 virtual_nodes.py > /tmp/virtual_nodes.log 2>&1 &
    echo "✅ Interactive virtual nodes started (PID: $!)"
    echo "📡 Virtual nodes support full device control"
    echo "🎮 Nodes will respond to LED on/off commands"
    echo "🔧 Override commands supported"
    
    sleep 2
    echo "📋 Simulator logs: tail -f /tmp/virtual_nodes.log"
    ;;

  sim)
    echo "🎮 Starting Cooja Simulation Mode..."
    echo "===================================="
    
    # Start backend services
    echo "🌐 Starting backend services..."
    docker compose up -d mosquitto mysql controller
    
    # Build Contiki-NG nodes
    echo "🔨 Building Contiki-NG firmware..."
    cd contiki_nodes
    make node1 TARGET=cooja
    make node2 TARGET=cooja
    make node3 TARGET=cooja
    cd ../contiki-ng/tools/cooja

    # If user passed --load <file>, use it
    if [ "$2" = "--load" ] && [ -n "$3" ]; then
        SIM_FILE=$PROJECT_DIR/$3
        echo "[*] Launching Cooja with simulation file: $SIM_FILE"
        ./gradlew run --args="$SIM_FILE"
    else
        echo "[*] Launching empty Cooja..."
        ./gradlew run
    fi
    ;;

  flash)
    echo "[*] Building firmware for nRF52840 hardware..."
    cd contiki_nodes
    make node1 TARGET=nrf52840dk
    make node2 TARGET=nrf52840dk
    make node3 TARGET=nrf52840dk
    echo "[*] Flash binaries manually using nrfjprog/openocd."
    ;;

  stop)
    echo "🛑 Stopping IoT Energy Management System..."
    
    # Stop Docker services
    docker compose down
    
    # Stop simulators
    if [ -f "$LOG_DIR/simulators.pid" ]; then
        kill $(cat "$LOG_DIR/simulators.pid") 2>/dev/null || true
        rm "$LOG_DIR/simulators.pid"
    fi
    pkill -f "python.*node.*sim" 2>/dev/null || true
    pkill -f "cooja" 2>/dev/null || true
    
    echo "✅ System stopped"
    ;;

  logs)
    if [ "$2" ]; then
        # Show specific service logs
        docker compose logs -f "$2"
    else
        # Show all logs
        echo "📋 System Logs:"
        echo "=============="
        echo "🐳 Docker Services:"
        docker compose logs --tail=50
        
        if [ -f "$LOG_DIR/simulators.log" ]; then
            echo ""
            echo "🎭 Simulators:"
            tail -20 "$LOG_DIR/simulators.log"
        fi
    fi
    ;;

  status)
    echo "📊 IoT System Status:"
    echo "===================="
    
    echo "🐳 Docker Services:"
    docker compose ps
    
    echo ""
    echo "🌐 Service Health:"
    curl -s http://localhost:5001/api/status 2>/dev/null | python3 -m json.tool || echo "❌ Controller API not responding"
    curl -s http://localhost:5000/api/status 2>/dev/null | python3 -m json.tool || echo "❌ WebApp not responding"
    
    if [ -f "$LOG_DIR/simulators.pid" ]; then
        echo "🎭 Simulators: Running (PID: $(cat $LOG_DIR/simulators.pid))"
    else
        echo "🎭 Simulators: Not running"
    fi
    ;;

  cli)
    shift  # Remove 'cli' argument
    echo "🖥️  CLI Interface:"
    
    if [ "$1" = "show" ]; then
        curl -s http://localhost:5001/api/sensor-data | python3 -m json.tool
    elif [ "$1" = "devices" ]; then
        curl -s http://localhost:5001/api/devices | python3 -m json.tool
    elif [ "$1" = "override" ] && [ "$2" ] && [ "$3" ] && [ "$4" ]; then
        # ./run.sh cli override node1 on 24h
        device_id="$2"
        status="$3"
        type="$4"
        curl -X POST http://localhost:5001/api/devices/$device_id/override \
            -H "Content-Type: application/json" \
            -d "{\"status\":\"$status\", \"type\":\"$type\"}" | python3 -m json.tool
    else
        echo "Usage:"
        echo "  ./run.sh cli show                           - Show recent sensor data"
        echo "  ./run.sh cli devices                        - Show device status"
        echo "  ./run.sh cli override <device> <on|off> <24h|permanent|disabled>  - Set override"
    fi
    ;;

  *)
    echo "IoT Energy Management System"
    echo "============================="
    echo ""
    echo "Usage: ./run.sh <command>"
    echo ""
    echo "Commands:"
    echo "  init             Initialize system and install dependencies"
    echo "  start [--virtual] Start complete system (--virtual includes simulated nodes)"
    echo "  stop             Stop all services"
    echo "  sim              Start with Cooja simulation"
    echo "  build            Build Docker containers"
    echo "  logs [svc]       Show logs (optional: specific service)"
    echo "  status           Show system status"
    echo "  cli <cmd>        Command-line interface"
    echo ""
    echo "🚀 Quick Start:"
    echo "  ./run.sh init           # First time setup"
    echo "  ./run.sh start --virtual # Start with virtual IoT nodes"
    echo "  ./run.sh stop           # Stop system"
    echo ""
    echo "🌍 Web Interface: http://localhost:5000"
    ;;

esac