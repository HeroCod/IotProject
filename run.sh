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
    make node1.node
    make node2.node
    make node3.node
    echo "[*] Launching Cooja..."
    cd ../contiki-ng/tools/cooja
    ant run
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