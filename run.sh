#!/bin/bash
# IoT Project - Unified Management Script
#
# Cloud-ready IoT Energy Management System
# Controller backend + Web frontend architecture
#
# Usage:
# Start contiki-ng for IPv6 tunnel
#   ./run.sh init         -> Initialize project and install dependencies
#   ./run.sh start        -> Start complete system (Docker + simulated nodes)
#   ./run.sh start --physical -> Start complete system with physical nodes
#   ./run.sh flash <node1|node2|node3|led-device|border-router> -> Build and flash firmware for specified node
#   ./run.sh stop         -> Stop all services
#   ./run.sh sim          -> Start with Cooja simulation
#   ./run.sh build        -> Build Docker containers
#   ./run.sh logs         -> Show logs
#   ./run.sh status       -> Show system status and ML performance
#   ./run.sh cleanup      -> Remove autocompletion from .bashrc
#   ./run.sh cleanup full -> Remove autocompletion and clean environment (venv, etc.)

# Detect if script is being sourced (for autocompletion only)
# When sourced, register completions silently and return
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    # Script is being sourced - register completions only
    _run_sh_completions() {
        local cur prev opts
        COMPREPLY=()
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"

        local commands="init build start stop sim flash logs status cleanup"
        local flash_targets="node1 node2 node3 led-device border-router mqtt-client"
        local services="controller webapp mosquitto mysql contiki-ng"

        case "${prev}" in
            flash)
                COMPREPLY=( $(compgen -W "${flash_targets}" -- ${cur}) )
                return 0
                ;;
            logs)
                COMPREPLY=( $(compgen -W "${services}" -- ${cur}) )
                return 0
                ;;
            start)
                COMPREPLY=( $(compgen -W "--physical" -- ${cur}) )
                return 0
                ;;
            sim)
                COMPREPLY=( $(compgen -W "--load" -- ${cur}) )
                return 0
                ;;
            cleanup)
                COMPREPLY=( $(compgen -W "full" -- ${cur}) )
                return 0
                ;;
            node1|node2|node3|led-device|border-router|mqtt-client)
                COMPREPLY=( $(compgen -W "clean" -- ${cur}) )
                return 0
                ;;
            ./run.sh|run.sh)
                COMPREPLY=( $(compgen -W "${commands}" -- ${cur}) )
                return 0
                ;;
            *)
                if [ ${COMP_CWORD} -eq 1 ]; then
                    COMPREPLY=( $(compgen -W "${commands}" -- ${cur}) )
                fi
                return 0
                ;;
        esac
    }
    
    complete -F _run_sh_completions ./run.sh
    complete -F _run_sh_completions run.sh
    return 0
fi

# If we reach here, script is being executed (not sourced)
# Bash completion function (legacy - only used when script is executed directly)
_run_sh_completions() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # Main commands
    local commands="init build start stop sim flash logs status cleanup"

    # Flash targets
    local flash_targets="node1 node2 node3 led-device border-router mqtt-client"

    # Docker services for logs
    local services="controller webapp mosquitto mysql contiki-ng"

    case "${prev}" in
        flash)
            COMPREPLY=( $(compgen -W "${flash_targets}" -- ${cur}) )
            return 0
            ;;
        logs)
            COMPREPLY=( $(compgen -W "${services}" -- ${cur}) )
            return 0
            ;;
        start)
            COMPREPLY=( $(compgen -W "--physical" -- ${cur}) )
            return 0
            ;;
        sim)
            COMPREPLY=( $(compgen -W "--load" -- ${cur}) )
            return 0
            ;;
        cleanup)
            COMPREPLY=( $(compgen -W "full" -- ${cur}) )
            return 0
            ;;
        node1|node2|node3|led-device|border-router|mqtt-client)
            COMPREPLY=( $(compgen -W "clean" -- ${cur}) )
            return 0
            ;;
        ./run.sh|run.sh)
            COMPREPLY=( $(compgen -W "${commands}" -- ${cur}) )
            return 0
            ;;
        *)
            if [ ${COMP_CWORD} -eq 1 ]; then
                COMPREPLY=( $(compgen -W "${commands}" -- ${cur}) )
            fi
            return 0
            ;;
    esac
}

# Register completion function (only when executed directly)
complete -F _run_sh_completions ./run.sh 2>/dev/null
complete -F _run_sh_completions run.sh 2>/dev/null

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

    # Add deadsnakes PPA for Python 3.10 on Ubuntu 24.04
    if ! dpkg -l | grep -q "python3.10"; then
        echo "   Adding deadsnakes PPA for Python 3.10..."
        sudo apt-get install -y software-properties-common
        sudo add-apt-repository -y ppa:deadsnakes/ppa
        sudo apt-get update
    fi

    sudo apt-get install -y git ant ca-certificates curl python3 python3-pip python3.10 python3.10-venv python3.10-dev binutils-arm-none-eabi gdb-arm-none-eabi wget tar srecord

    echo "🔧 Ensuring GCC 10 is installed..."
    # Check if gcc-10 is installed
    if ! dpkg -l | grep -q "gcc-10"; then
        echo "   Installing gcc-10 and g++-10..."
        sudo apt-get install -y gcc-10 g++-10
    else
        echo "   ✅ GCC 10 already installed"
    fi

    # Set gcc-10 as default using update-alternatives
    echo "   Setting GCC 10 as default compiler..."
    sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-10 100 --slave /usr/bin/g++ g++ /usr/bin/g++-10

    # Verify installation
    GCC_VERSION=$(gcc --version | head -n1)
    echo "   Current GCC version: $GCC_VERSION"

    echo "🔧 Installing ARM GCC 10.3.1 for embedded development..."
    ARM_GCC_DIR="/opt/gcc-arm-none-eabi-10.3-2021.10"
    if [ ! -d "$ARM_GCC_DIR" ]; then
        echo "   Downloading ARM GCC 10.3.1..."
        cd /tmp
        wget -q --show-progress https://developer.arm.com/-/media/Files/downloads/gnu-rm/10.3-2021.10/gcc-arm-none-eabi-10.3-2021.10-x86_64-linux.tar.bz2
        echo "   Extracting ARM GCC toolchain..."
        sudo tar -xjf gcc-arm-none-eabi-10.3-2021.10-x86_64-linux.tar.bz2 -C /opt/
        rm gcc-arm-none-eabi-10.3-2021.10-x86_64-linux.tar.bz2
        cd "$PROJECT_DIR"
        echo "   ✅ ARM GCC 10.3.1 installed to $ARM_GCC_DIR"
    else
        echo "   ✅ ARM GCC 10.3.1 already installed"
    fi

    # Add ARM GCC to PATH in current session and make it permanent
    if ! grep -q "$ARM_GCC_DIR/bin" ~/.bashrc; then
        echo "export PATH=\"$ARM_GCC_DIR/bin:\$PATH\"" >> ~/.bashrc
        echo "   Added ARM GCC to PATH in ~/.bashrc"
    fi
    export PATH="$ARM_GCC_DIR/bin:$PATH"

    # Verify ARM GCC installation
    if command -v arm-none-eabi-gcc &> /dev/null; then
        ARM_GCC_VERSION=$(arm-none-eabi-gcc --version | head -n1)
        echo "   ARM GCC version: $ARM_GCC_VERSION"
    fi

    echo "Installing Docker..."
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

    echo "🔧 Initializing Contiki-NG"
    if [ ! -d "contiki-ng" ] || [ -z "$(ls -A contiki-ng 2>/dev/null)" ]; then
        if [ -d "contiki-ng" ]; then
            echo "⚠️  Contiki-NG directory exists but is empty, cloning repository..."
        fi
        git clone --recurse-submodules --branch release/v5.0 https://github.com/contiki-ng/contiki-ng.git
        cd contiki-ng/tools/serial-io
        make
    else
        echo "✅ Contiki-NG already cloned"
    fi

    echo "🔧 Setting up Python 3.10 virtual environment for nrfutil and ML tools..."

    # Verify Python 3.10 is available
    if ! command -v python3.10 &> /dev/null; then
        echo "❌ Python 3.10 not found. Please install it first."
        exit 1
    fi

    # Remove old/corrupted venv if it exists but is broken
    if [ -d "$PROJECT_DIR/venv" ] && [ ! -f "$PROJECT_DIR/venv/bin/pip" ]; then
        echo "   Removing corrupted virtual environment..."
        rm -rf "$PROJECT_DIR/venv"
    fi

    # Create venv with Python 3.10
    if [ ! -d "$PROJECT_DIR/venv" ]; then
        echo "   Creating new Python 3.10 virtual environment..."
        python3.10 -m venv "$PROJECT_DIR/venv"
        if [ $? -ne 0 ]; then
            echo "❌ Failed to create virtual environment"
            exit 1
        fi
    else
        echo "   Python virtual environment already exists"
    fi

    # Verify venv was created successfully
    if [ ! -f "$PROJECT_DIR/venv/bin/pip" ]; then
        echo "❌ Virtual environment pip not found. Venv creation failed."
        exit 1
    fi

    # Install all dependencies in the venv
    echo "📦 Installing project dependencies in Python 3.10 virtual environment..."
    echo "   This includes: nrfutil, scikit-learn, tensorflow, emlearn, and more..."
    echo "   (This may take a few minutes...)"

    "$PROJECT_DIR/venv/bin/pip" install --upgrade pip wheel setuptools
    if [ $? -ne 0 ]; then
        echo "❌ Failed to upgrade pip"
        exit 1
    fi

    "$PROJECT_DIR/venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install requirements"
        exit 1
    fi

    # Verify nrfutil installation
    echo ""
    echo "🔍 Verifying installations..."
    if [ -f "$PROJECT_DIR/venv/bin/nrfutil" ]; then
        NRFUTIL_VERSION=$("$PROJECT_DIR/venv/bin/nrfutil" version 2>/dev/null || echo "unknown")
        echo "✅ nrfutil: $NRFUTIL_VERSION"

        # Test pkg command
        if "$PROJECT_DIR/venv/bin/nrfutil" pkg --help &> /dev/null; then
            echo "✅ nrfutil pkg command: OK"
        else
            echo "⚠️  nrfutil pkg command not available"
        fi
    else
        echo "❌ nrfutil not installed"
    fi

    # Verify ML packages
    echo ""
    echo "📊 Verifying ML/Data Science packages..."

    PACKAGES_OK=true

    if "$PROJECT_DIR/venv/bin/python" -c "import sklearn" 2>/dev/null; then
        SKLEARN_VER=$("$PROJECT_DIR/venv/bin/python" -c "import sklearn; print(sklearn.__version__)")
        echo "✅ scikit-learn: $SKLEARN_VER"
    else
        echo "❌ scikit-learn not installed"
        PACKAGES_OK=false
    fi

    if "$PROJECT_DIR/venv/bin/python" -c "import numpy" 2>/dev/null; then
        NUMPY_VER=$("$PROJECT_DIR/venv/bin/python" -c "import numpy; print(numpy.__version__)")
        echo "✅ numpy: $NUMPY_VER"
    else
        echo "❌ numpy not installed"
        PACKAGES_OK=false
    fi

    if "$PROJECT_DIR/venv/bin/python" -c "import pandas" 2>/dev/null; then
        PANDAS_VER=$("$PROJECT_DIR/venv/bin/python" -c "import pandas; print(pandas.__version__)")
        echo "✅ pandas: $PANDAS_VER"
    else
        echo "❌ pandas not installed"
        PACKAGES_OK=false
    fi

    if "$PROJECT_DIR/venv/bin/python" -c "import emlearn" 2>/dev/null; then
        EMLEARN_VER=$("$PROJECT_DIR/venv/bin/python" -c "import emlearn; print(emlearn.__version__)")
        echo "✅ emlearn: $EMLEARN_VER"
    else
        echo "⚠️  emlearn not installed (optional for model export)"
    fi

    if "$PROJECT_DIR/venv/bin/python" -c "import tensorflow" 2>/dev/null; then
        TF_VER=$("$PROJECT_DIR/venv/bin/python" -c "import tensorflow; print(tensorflow.__version__)")
        echo "✅ tensorflow: $TF_VER"
    else
        echo "⚠️  tensorflow not installed (optional for LSTM models)"
    fi

    if [ "$PACKAGES_OK" = false ]; then
        echo ""
        echo "⚠️  Some required packages failed to install"
        echo "   Check the error messages above"
    fi

    echo ""
    echo "💡 To use the virtual environment:"
    echo "   Activate: source venv/bin/activate"
    echo "   Run Python scripts: ./venv/bin/python <script.py>"
    echo "   Run Jupyter: ./venv/bin/jupyter notebook"

    echo "🔧 Setting up bash autocompletion..."
    COMPLETION_LINE="source $PROJECT_DIR/run.sh"
    if ! grep -Fq "source $PROJECT_DIR/run.sh" ~/.bashrc; then
        echo "" >> ~/.bashrc
        echo "# IoT Project run.sh autocompletion" >> ~/.bashrc
        echo "$COMPLETION_LINE" >> ~/.bashrc
        echo "   ✅ Bash autocompletion added to ~/.bashrc"
        echo "   💡 Run 'source ~/.bashrc' or start a new terminal to enable it"
    else
        echo "   ✅ Bash autocompletion already configured"
    fi

    echo "Firewall configuration: Allowing MQTT port 1883"
    sudo ufw allow 1883

    # Making now sure that ipv6 and ipv4 forwarding are enabled
    echo "Enabling IPv4 and IPv6 forwarding"
    sudo sysctl -w net.ipv4.ip_forward=1
    sudo sysctl -w net.ipv6.conf.all.forwarding=1

    echo "🔧 Configuring serial port permissions..."
    # Add user to dialout group for serial port access (no sudo needed)
    if ! groups $USER | grep -q "\bdialout\b"; then
        echo "   Adding $USER to 'dialout' group for serial port access..."
        sudo usermod -aG dialout $USER
        echo "   ⚠️  You need to LOG OUT and LOG BACK IN for serial port permissions to take effect!"
        echo "   (Or run: newgrp dialout)"
    else
        echo "   ✅ User already in 'dialout' group"
    fi

    # Optionally create udev rules for Nordic devices
    UDEV_RULES_FILE="/etc/udev/rules.d/99-nordic-devices.rules"
    if [ ! -f "$UDEV_RULES_FILE" ]; then
        echo "   Creating udev rules for Nordic devices..."
        cat << 'EOF' | sudo tee "$UDEV_RULES_FILE" > /dev/null
# Nordic Semiconductor devices
# nRF52840 Dongle in DFU mode
SUBSYSTEM=="usb", ATTRS{idVendor}=="1915", ATTRS{idProduct}=="521f", MODE="0666", GROUP="dialout"
# nRF52840 Dongle in CDC ACM mode
SUBSYSTEM=="tty", ATTRS{idVendor}=="1915", ATTRS{idProduct}=="c00a", MODE="0666", GROUP="dialout"
# All Nordic Semiconductor devices
SUBSYSTEM=="usb", ATTRS{idVendor}=="1915", MODE="0666", GROUP="dialout"
EOF
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        echo "   ✅ Nordic udev rules created"
    else
        echo "   ✅ Nordic udev rules already exist"
    fi

    echo ""
    echo "✅ Initialization complete!"
    echo ""
    echo "💡 Next steps:"
    if ! groups $USER | grep -q "\bdialout\b"; then
        echo "   ⚠️  IMPORTANT: Log out and back in (or run: newgrp dialout)"
        echo "   This is required for serial port access without sudo"
        echo ""
    fi
    echo "   1. If you just joined 'dialout' group: Log out and back in"
    echo "   2. Enable autocompletion: source ~/.bashrc (or start a new terminal)"
    echo "   3. Run: ./run.sh start"
    echo ""
    echo "💡 Autocompletion is now available! Try:"
    echo "   ./run.sh <Tab><Tab>         # See all commands"
    echo "   ./run.sh flash <Tab><Tab>   # See all flashable nodes"
    echo "   ./run.sh logs <Tab><Tab>    # See all services"
    ;;

  build)
    echo "🔨 Building IoT system containers..."
    docker compose build
    echo "✅ Build complete!"
    ;;

  start)
    if [ "$2" = "--physical" ]; then
        echo "🚀 Starting Complete IoT Energy Management System with Physical Nodes..."
        echo "======================================================================="

        # Build containers if needed
        if ! docker images | grep -q iotproject-controller; then
            echo "📦 Building containers..."
            docker compose build
        fi

        # Start core services (no serial-bridge yet)
        echo "🌐 Starting core services (MySQL, MQTT, Controller, WebApp)..."
        docker compose up -d --force-recreate

        # Assume border router is always at /dev/ttyACM0
        BORDER_ROUTER_DEVICE="/dev/ttyACM0"
        SENSOR_DEVICES=()

        # Optional: Check if device exists
        if [ ! -e "$BORDER_ROUTER_DEVICE" ]; then
            echo "❌ Border router device not found at $BORDER_ROUTER_DEVICE"
            exit 1
        fi

        # Build contiki-ng container if needed
        if ! docker images | grep -q iotproject-contiki-ng; then
            echo "🔨 Building contiki-ng container..."
            docker build -t contiki-ng ./contiki-container
        fi

        # Start tunslip6 inside contiki-ng container
        echo "🌉 Starting tunslip6 IPv6 tunnel..."
        sudo ./contiki-ng/tools/serial-io/tunslip6 -s "$BORDER_ROUTER_DEVICE" fd00::1/64 > "$LOG_DIR/tunslip6.log" 2>&1 &
        sudo chown -R $USER:$USER "$PROJECT_DIR"
        echo "✅ System with physical nodes started successfully!"
        echo ""
        echo "🔗 IPv6 Tunnel: fd00::/64 via tunslip6"
        echo "📡 Border Router: $BORDER_ROUTER_DEVICE"
        if [ ${#SENSOR_DEVICES[@]} -gt 0 ]; then
            echo "📱 Sensor Nodes:"
            for device in "${SENSOR_DEVICES[@]}"; do
                echo "   - $device"
            done
        fi
        echo ""
        echo "📝 Monitor tunslip6: docker logs -f contiki-ng"
        echo "🔍 Monitor bridge: docker compose logs -f serial-bridge"

    else
        echo "🚀 Starting Complete IoT Energy Management System..."
        echo "=================================================="

        # Build containers if needed
        if ! docker images | grep -q iotproject-controller; then
            echo "📦 Building containers..."
            docker compose build
        fi

        # Start all services
        echo "🌐 Starting all services..."
        docker compose up -d --force-recreate
        sudo chown -R $USER:$USER "$PROJECT_DIR"

        echo "✅ System started successfully!"
        echo ""
        echo "ℹ️  Note: Physical nodes require './run.sh start --physical' for device connectivity"
    fi

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
    echo ""
    echo "📝 View logs with: ./run.sh logs [service-name]"
    ;;

  sim)
    echo "🎮 Starting Cooja Simulation Mode..."
    echo "===================================="

    # Start backend services
    echo "🌐 Starting backend services..."
    docker compose up -d --force-recreate mosquitto mysql controller

    cd contiki-ng/tools/cooja

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
    TARGET_NODE=$2
    CLEAN_BUILD=$3
    if [ -z "$TARGET_NODE" ]; then
        echo "Usage: ./run.sh flash <node1|node2|node3|led-device|border-router|mqtt-client> [clean]"
        echo "Builds and flashes the firmware for the specified node."
        echo "Add 'clean' to run distclean before building."
        echo "Connect one device at a time before running the command."
        exit 1
    fi

    # Check for nrfutil in venv
    NRFUTIL_PATH="$PROJECT_DIR/venv/bin/nrfutil"
    if [ ! -f "$NRFUTIL_PATH" ]; then
        echo "❌ nrfutil not found in virtual environment."
        echo "   Please run: ./run.sh init"
        exit 1
    fi

    # Verify it has the pkg command
    if ! "$NRFUTIL_PATH" pkg --help &> /dev/null; then
        echo "❌ nrfutil 'pkg' command not available."
        echo "   Please run: ./run.sh init"
        exit 1
    fi

    echo "🔌 Flashing firmware for $TARGET_NODE using DFU..."

    # Auto-detect Nordic DFU/CDC port
    DFU_PORT=""
    CDC_PORT=""
    echo "🔍 Searching for Nordic devices..."
    for port in /dev/ttyACM*; do
        if [ -e "$port" ]; then
            echo "scanned port $port"
            # Check if it's a Nordic device (VID 1915)
            if udevadm info -a -n "$port" | grep Nordic; then
                # Check if it's in DFU mode (PID 521f)
                if udevadm info -a -n "$port" | grep DFU; then
                    DFU_PORT="$port"
                    echo "✅ Found Nordic DFU device at $DFU_PORT"
                    break # Found DFU device, no need to search further
                # Check if it's in CDC/Application mode (PID c00a)
                elif udevadm info -a -n "$port" | grep CDC; then
                    CDC_PORT="$port"
                    echo "ℹ️ Found Nordic device in Application mode at $CDC_PORT (will not flash)"
                fi
            fi
        fi
    done

    # Decide what to do based on what was found
    if [ -z "$DFU_PORT" ]; then
        if [ -n "$CDC_PORT" ]; then
            # A device was found, but it's in the wrong mode
            echo "  A Nordic device was found at $CDC_PORT, but it is not in DFU mode."
            echo "  Please put the device into DFU mode by pressing the RESET button."
            echo "  The device's LED should start pulsing red."
        else
            # No Nordic devices were found at all
            echo "No Nordic device found on any /dev/ttyACM* port."
            echo "   Please ensure the device is connected and in DFU mode."
        fi
        exit 1
    fi


    echo "✅ Ready to flash device at $DFU_PORT"

    if [[ "$TARGET_NODE" == "node1" || "$TARGET_NODE" == "node2" || "$TARGET_NODE" == "node3" || "$TARGET_NODE" == "led-device" || "$TARGET_NODE" == "mqtt-client" ]]; then
        echo "   Building and flashing $TARGET_NODE firmware via DFU..."
        (
            cd contiki_nodes/$TARGET_NODE

            # Ensure GCC-10 and ARM GCC 10.3.1 are used for compilation
            export CC=gcc-10
            export CXX=g++-10
            export PATH="/opt/gcc-arm-none-eabi-10.3-2021.10/bin:$PATH"
            echo "   Using compiler: $(gcc-10 --version | head -n1)"
            echo "   Using ARM compiler: $(arm-none-eabi-gcc --version | head -n1)"

            if [ "$CLEAN_BUILD" = "clean" ]; then
                make distclean
                echo ""
                echo "--- Cleaned Directory before flashing ---"
                echo ""
            fi
            # Use nrfutil from venv (Python 3.10 with nrfutil 6.1.7)
            make $TARGET_NODE.dfu-upload TARGET=nrf52840 BOARD=dongle PORT="$DFU_PORT" NRFUTIL="$PROJECT_DIR/venv/bin/nrfutil"
            echo ""
        )

        if [ $? -eq 0 ]; then
            echo "✅ $TARGET_NODE flashed successfully via DFU."
        else
            echo "❌ Failed to flash $TARGET_NODE."
            exit 1
        fi

    elif [ "$TARGET_NODE" == "border-router" ]; then
        echo "   Building and flashing $TARGET_NODE firmware via DFU..."
        echo "NB: This will connect with tunslip and make command, so execute last"
        (
            cd contiki_nodes/$TARGET_NODE

            # Ensure GCC-10 and ARM GCC 10.3.1 are used for compilation
            export CC=gcc-10
            export CXX=g++-10
            export PATH="/opt/gcc-arm-none-eabi-10.3-2021.10/bin:$PATH"
            echo "   Using compiler: $(gcc-10 --version | head -n1)"
            echo "   Using ARM compiler: $(arm-none-eabi-gcc --version | head -n1)"

            if [ "$CLEAN_BUILD" = "clean" ]; then
                make distclean
                echo ""
                echo "--- Cleaned Directory before flashing ---"
                echo ""
            fi
            # Use nrfutil from venv (Python 3.10 with nrfutil 6.1.7)
            make $TARGET_NODE.dfu-upload TARGET=nrf52840 BOARD=dongle PORT="$DFU_PORT" NRFUTIL="$PROJECT_DIR/venv/bin/nrfutil"
            sleep 1
            make $TARGET_NODE TARGET=nrf52840 connect-router BOARD=dongle PORT="$DFU_PORT" NRFUTIL="$PROJECT_DIR/venv/bin/nrfutil"
            echo "Border-Router closed"
        )

        if [ $? -eq 0 ]; then
            echo "✅ $TARGET_NODE flashed successfully via DFU."
        else
            echo "❌ Failed to flash $TARGET_NODE."
            exit 1
        fi
    else
        echo "❌ Unknown target: $TARGET_NODE. Use node1, node2, node3, led-device or border-router"
        exit 1
    fi
    ;;

  stop)
    echo "🛑 Stopping IoT Energy Management System..."

    # Stop Docker services
    docker compose down 2>/dev/null || true

    # Stop any standalone simulators
    if [ -f "$LOG_DIR/simulators.pid" ]; then
        kill $(cat "$LOG_DIR/simulators.pid") 2>/dev/null || true
        rm "$LOG_DIR/simulators.pid"
    fi
    pkill -f "tunslip6" 2>/dev/null || true

    echo "✅ System stopped"
    ;;

  logs)
    if [ "$2" ]; then
        # Show specific service logs
        if [ "$2" = "contiki-ng" ]; then
            # Check if contiki-ng container is running
            if docker ps | grep -q contiki-ng; then
                docker logs -f contiki-ng
            else
                echo "❌ contiki-ng container not running. Start with: ./run.sh start --physical"
            fi
        else
            # Try regular compose file
            docker compose logs -f "$2"
        fi
    else
        # Show all logs
        echo "📋 System Logs:"
        echo "=============="
        echo "🐳 Docker Services:"
        docker compose logs --tail=50

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
    docker compose ps

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

  cleanup)
    echo "🧹 Cleaning up IoT Project configuration..."
    echo "=========================================="
    
    BASHRC_FILE="$HOME/.bashrc"
    BACKUP_FILE="$HOME/.bashrc.iot-backup-$(date +%Y%m%d-%H%M%S)"
    PROJECT_DIR=$(pwd)
    
    # Check if autocompletion is configured
    if grep -Fq "# IoT Project run.sh autocompletion" "$BASHRC_FILE"; then
        echo "📝 Backing up .bashrc to $BACKUP_FILE"
        cp "$BASHRC_FILE" "$BACKUP_FILE"
        
        echo "🗑️  Removing autocompletion from .bashrc..."
        # Remove the IoT Project autocompletion lines
        # This removes the comment line, the source line, and any empty lines between them
        sed -i '/# IoT Project run.sh autocompletion/,/source.*run\.sh/d' "$BASHRC_FILE"
        
        # Clean up any multiple consecutive empty lines left behind (max 2)
        sed -i '/^$/N;/^\n$/N;/^\n\n$/d' "$BASHRC_FILE"
        
        echo "   ✅ Autocompletion removed from .bashrc"
        echo "   💾 Backup saved to: $BACKUP_FILE"
    else
        echo "   ℹ️  No autocompletion found in .bashrc"
    fi
    
    # Check for ARM GCC path in .bashrc
    if grep -q "/opt/gcc-arm-none-eabi-10.3-2021.10/bin" "$BASHRC_FILE"; then
        echo "   ℹ️  ARM GCC PATH entry found in .bashrc (keeping it as it may be needed)"
    fi
    
    if [ "$2" = "full" ]; then
        echo ""
        echo "🧹 Full cleanup requested - removing environment..."
        
        # Stop any running services
        if docker compose ps 2>/dev/null | grep -q "Up"; then
            echo "   🛑 Stopping Docker services..."
            docker compose down 2>/dev/null || true
        fi
        
        # Remove Python virtual environment
        if [ -d "$PROJECT_DIR/venv" ]; then
            echo "   🗑️  Removing Python virtual environment..."
            rm -rf "$PROJECT_DIR/venv"
            echo "      ✅ venv/ removed"
        fi
        
        # Remove logs
        if [ -d "$PROJECT_DIR/logs" ]; then
            echo "   🗑️  Removing logs..."
            rm -rf "$PROJECT_DIR/logs"
            echo "      ✅ logs/ removed"
        fi
        
        # Remove mosquitto data
        if [ -d "$PROJECT_DIR/mosquitto/data" ] || [ -d "$PROJECT_DIR/mosquitto/log" ]; then
            echo "   🗑️  Removing mosquitto data and logs..."
            rm -rf "$PROJECT_DIR/mosquitto/data" "$PROJECT_DIR/mosquitto/log"
            echo "      ✅ mosquitto data/logs removed"
        fi
        
        # Optional: Ask about removing Docker images
        echo ""
        echo "   ⚠️  Docker images and volumes were NOT removed."
        echo "      To remove them manually, run:"
        echo "      docker compose down -v --rmi all"
        
        echo ""
        echo "   ⚠️  ARM GCC toolchain in /opt/gcc-arm-none-eabi-10.3-2021.10 was NOT removed."
        echo "      To remove it manually, run:"
        echo "      sudo rm -rf /opt/gcc-arm-none-eabi-10.3-2021.10"
        
        echo ""
        echo "✅ Full cleanup complete!"
    else
        echo ""
        echo "✅ Cleanup complete! Autocompletion removed."
        echo "   💡 To also clean the environment (venv, logs, etc.), run:"
        echo "      ./run.sh cleanup full"
    fi
    
    echo ""
    echo "📋 To apply .bashrc changes, run: source ~/.bashrc"
    echo "   Or simply open a new terminal."
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
    echo "  start --physical     Start complete system with physical IoT nodes"
    echo "  stop                 Stop all services"
    echo "  sim                  Start with Cooja simulation"
    echo "  build                Build Docker containers"
    echo "  flash <node> [clean] Flash firmware to specified node"
    echo "  logs [service]       Show logs (optional: specific service)"
    echo "  status               Show system status and ML performance"
    echo "  cleanup              Remove autocompletion from .bashrc"
    echo "  cleanup full         Remove autocompletion and clean environment (venv, logs)"
    echo ""
    echo "🚀 Quick Start:"
    echo "  ./run.sh init               # First time setup"
    echo "  ./run.sh start --physical   # Start with physical IoT nodes"
    echo "  ./run.sh logs contiki-ng    # View tunslip6 logs"
    echo "  ./run.sh stop               # Stop system"
    echo ""
    echo "🌍 Web Interface: http://localhost:5000"
    echo "🔧 API Interface: http://localhost:5001/api/status"
    ;;

esac