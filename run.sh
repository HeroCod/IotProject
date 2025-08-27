#!/bin/bash
# IoT Project - unified runner script
# Usage:
#   ./run.sh build        -> build docker containers
#   ./run.sh backend      -> start docker infra (MySQL + Mosquitto + Collector)
#   ./run.sh stop         -> stop docker compose
#   ./run.sh sim          -> build node firmwares for simulation + open Cooja
#   ./run.sh flash        -> build binaries for nRF52840 hardware boards
#   ./run.sh cli show     -> run CLI to query DB
#   ./run.sh cli set <id> <on|off> -> send actuator command to a node

PROJECT_DIR=$(pwd)

case "$1" in
  init)
    echo "[*] Initializing project and system from scratch..."
    echo "[*] Installing dependencies..."
    sudo apt-get update
    sudo apt-get install install ant git git-lfs ant ca-certificates curl -y
    # Install Docker
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
        $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y
    sudo groupadd docker
    sudo usermod -aG docker $USER
    newgrp docker
    echo "[*] Cloning Contiki-NG repository..."
    if [ ! -d "contiki-ng/tools" ]; then
      git clone --recurse-submodules https://github.com/contiki-ng/contiki-ng.git ./contiki-ng
    fi
    echo "[*] Init done."
  ;;
  build)
    echo "[*] Building Docker containers..."
    docker compose build
    ;;

  backend)
    echo "[*] Starting Docker backend (Mosquitto + MySQL + Collector)..."
    docker compose up
    ;;

  stop)
    echo "[*] Stopping all containers..."
    docker compose down -v
    ;;

  sim)
    echo "[*] Building firmware for simulated nodes..."
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

  cli)
    shift
    if [ "$1" = "show" ]; then
      docker compose run cli show-data
    elif [ "$1" = "set" ]; then
      shift
      docker compose run cli set "$1" "$2"
    else
      echo "Usage: ./run.sh cli show | ./run.sh cli set <device_id> <on|off>"
    fi
    ;;

  *)
    echo "Usage:"
    echo "  ./run.sh build        -> build docker containers"
    echo "  ./run.sh backend      -> start docker backend"
    echo "  ./run.sh stop         -> stop backend"
    echo "  ./run.sh sim          -> build node firmwares + open Cooja"
    echo "  ./run.sh flash        -> build binaries for nRF52840 boards"
    echo "  ./run.sh cli show     -> show DB data"
    echo "  ./run.sh cli set id on|off -> set actuator state"
    ;;
esac