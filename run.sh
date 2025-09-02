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
        
        # Build containers if needed
        if ! docker images | grep -q iot_controller; then
            echo "📦 Building containers..."
            docker compose -f docker-compose.virtual.yml build
        fi
        
        # Start all services including virtual nodes
        echo "🌐 Starting all services (MySQL, MQTT, Controller, WebApp, Virtual Nodes)..."
        docker compose -f docker-compose.virtual.yml up -d
        
        echo "✅ System with virtual nodes started successfully!"
        echo ""
        echo "🎭 Virtual IoT Nodes: Running in Docker container"
        echo "   - node1: Living Room"
        echo "   - node2: Kitchen"  
        echo "   - node3: Bedroom"
        echo "   🔍 View virtual node logs: docker compose -f docker-compose.virtual.yml logs virtual-nodes"
        
    else
        echo "🚀 Starting Complete IoT Energy Management System..."
        echo "=================================================="
        
        # Build containers if needed
        if ! docker images | grep -q iot_controller; then
            echo "📦 Building containers..."
            docker compose build
        fi
        
        # Start core services only
        echo "� Starting core services (MySQL, MQTT, Controller, WebApp)..."
        docker compose up -d
        
        echo "✅ Core system started successfully!"
        echo ""
        echo "ℹ️  Virtual nodes not started. Use './run.sh start --virtual' to include them."
    fi
    
    # Wait for services to be ready
    echo "⏳ Waiting for services to start..."
    sleep 10
    
    echo ""
    echo "🌍 Access points:"
    echo "   📊 Web Dashboard:    http://localhost:5000"
    echo "   📈 Analytics:        http://localhost:5000/analytics"
    echo "   🤖 AI Optimizer:    http://localhost:5000/optimizer"
    echo "   🔧 Controller API:   http://localhost:5001/api/status"
    echo ""
    echo "📋 System status:"
    echo "   MQTT Broker:    localhost:1883"
    echo "   MySQL DB:       localhost:3306"
    echo "   Controller:     localhost:5001"
    echo "   WebApp:         localhost:5000"
    if [ "$2" = "--virtual" ]; then
        echo "   Virtual Nodes:  Docker container"
    fi
    echo ""
    echo "📝 View logs with: ./run.sh logs [service-name]"
    ;;

  start-simulators)
    echo "🎭 Starting interactive virtual IoT nodes..."
    
    # Kill any existing simulators
    pkill -f "python.*virtual_nodes" 2>/dev/null || true
    
    # Check if virtual_nodes.py exists
    if [ ! -f "virtual_nodes/virtual_nodes.py" ]; then
        echo "❌ No simulator found!"
        return 1
    fi
    
    # Start the new interactive virtual nodes
    echo "🚀 Starting interactive virtual nodes system..."
    cd virtual_nodes
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
    
    # Stop Docker services (try both compose files)
    docker compose down 2>/dev/null || true
    docker compose -f docker-compose.virtual.yml down 2>/dev/null || true
    
    # Stop any standalone simulators
    if [ -f "$LOG_DIR/simulators.pid" ]; then
        kill $(cat "$LOG_DIR/simulators.pid") 2>/dev/null || true
        rm "$LOG_DIR/simulators.pid"
    fi
    pkill -f "python.*virtual_nodes" 2>/dev/null || true
    pkill -f "cooja" 2>/dev/null || true
    
    echo "✅ System stopped"
    ;;

  logs)
    if [ "$2" ]; then
        # Show specific service logs
        if [ "$2" = "virtual-nodes" ]; then
            # Check if virtual compose file is running
            if docker compose -f docker-compose.virtual.yml ps | grep -q virtual-nodes; then
                docker compose -f docker-compose.virtual.yml logs -f virtual-nodes
            else
                echo "❌ Virtual nodes container not running. Start with: ./run.sh start --virtual"
            fi
        else
            # Try regular compose file first, then virtual
            docker compose logs -f "$2" 2>/dev/null || docker compose -f docker-compose.virtual.yml logs -f "$2"
        fi
    else
        # Show all logs - check which compose file is running
        echo "📋 System Logs:"
        echo "=============="
        echo "🐳 Docker Services:"
        
        if docker compose -f docker-compose.virtual.yml ps | grep -q virtual-nodes; then
            echo "   (Virtual mode - with simulated nodes)"
            docker compose -f docker-compose.virtual.yml logs --tail=50
        else
            echo "   (Standard mode)"
            docker compose logs --tail=50
        fi
        
        if [ -f "$LOG_DIR/simulators.log" ]; then
            echo ""
            echo "🎭 Standalone Simulators:"
            tail -20 "$LOG_DIR/simulators.log"
        fi
    fi
    ;;

  status)
    echo "📊 IoT System Status:"
    echo "===================="
    
    echo "🐳 Docker Services:"
    # Check which compose file is running
    if docker compose -f docker-compose.virtual.yml ps | grep -q virtual-nodes; then
        echo "   (Virtual mode - with simulated nodes)"
        docker compose -f docker-compose.virtual.yml ps
    else
        echo "   (Standard mode)"
        docker compose ps
    fi
    
    echo ""
    echo "🌐 Service Health:"
    curl -s http://localhost:5001/api/status 2>/dev/null | python3 -m json.tool || echo "❌ Controller API not responding"
    
    echo ""
    echo "🤖 ML Model Performance:"
    curl -s http://localhost:5001/api/baseline-comparison 2>/dev/null | python3 -m json.tool || echo "❌ Baseline comparison not available"
    
    if [ -f "$LOG_DIR/simulators.pid" ]; then
        echo "🎭 Standalone Simulators: Running (PID: $(cat $LOG_DIR/simulators.pid))"
    else
        echo "🎭 Standalone Simulators: Not running"
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
    echo "  init                 Initialize system and install dependencies"
    echo "  start                Start core system (MySQL, MQTT, Controller, WebApp)"
    echo "  start --virtual      Start complete system with Docker-based virtual IoT nodes"
    echo "  stop                 Stop all services"
    echo "  sim                  Start with Cooja simulation"
    echo "  build                Build Docker containers"
    echo "  logs [service]       Show logs (optional: specific service)"
    echo "  status               Show system status and ML performance"
    echo "  cli <cmd>            Command-line interface"
    echo ""
    echo "🚀 Quick Start:"
    echo "  ./run.sh init               # First time setup"
    echo "  ./run.sh start --virtual    # Start with virtual IoT nodes (Docker)"
    echo "  ./run.sh logs virtual-nodes # View virtual node logs"
    echo "  ./run.sh stop               # Stop system"
    echo ""
    echo "� Virtual Nodes:"
    echo "  --virtual flag starts containerized IoT nodes that:"
    echo "  • Simulate realistic sensor data (temperature, light, occupancy)"
    echo "  • Respond to ML-driven lighting control commands"
    echo "  • Support manual overrides from the web interface"
    echo "  • Follow time-based behavioral patterns"
    echo ""
    echo "�🌍 Web Interface: http://localhost:5000"
    echo "🔧 API Interface: http://localhost:5001/api/status"
    ;;

esac