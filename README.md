# IoT Project: Smart Lighting with MQTT, Docker & Contiki-NG Simulation

This project demonstrates a **Smart Home Lighting IoT** system for the IoT course project (solo setup).  
Components:

- **3 IoT Nodes** (simulated in Cooja with Contiki-NG) → publish simulated light sensor values and control an LED.
- **MQTT Broker** (Mosquitto in Docker).
- **Collector App** (Python container) → stores sensor data in MySQL and applies an ML-based decision (turn LED ON/OFF).
- **CLI App** (Python container) → lets user override actuator state or query recent sensor data.

---

## 📂 Project Structure

```markdown
iot-project/
│
├── docker-compose.yml
├── run.sh
├── README.md
│
├── config/
│   ├── devices.json
│   └── mosquitto.conf
│
├── collector/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── collector.py
│   └── entrypoint.sh
│
├── cli/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── control.py
│
├── contiki_nodes/
│   ├── Makefile
│   ├── node1.c
│   ├── node2.c
│   ├── node3.c
│   └── README.md
│
└── ml/
    ├── train_model.ipynb
    └── model_params.json
```

---

## 🛠 1. Prerequisites

- **Docker & Docker Compose**
- **Java JDK + ant** (to run Cooja simulator)
- **Contiki-NG** installed locally: [https://github.com/contiki-ng/contiki-ng](https://github.com/contiki-ng/contiki-ng)
- **Python 3.10+** (if running CLI outside Docker)

---

## 🚀 2. Quick Start with `run.sh`

All commands are wrapped inside **one script** for consistency.

### Build everything

```bash
./run.sh build
```

### Start backend (MQTT + MySQL + Collector)

```bash
./run.sh backend
```

### Stop backend

```bash
./run.sh stop
```

---

## 🎛 3. Simulate IoT Nodes (Cooja)

1. Build simulated firmwares:

    ```bash
    ./run.sh sim
    ```

    This compiles `node1.node`, `node2.node`, `node3.node` and launches Cooja.

2. In Cooja:
   - Add a border router node. Broker IP should match Docker’s Mosquitto (`localhost` mapped).
   - Add Node1, Node2, Node3.
   - Nodes publish random light sensor values to MQTT topics:
     - `sensors/node1/light`
     - `sensors/node2/light`
     - `sensors/node3/light`
   - Nodes subscribe to their actuator topics:
     - `actuators/node1/led`, etc.
   - Simulated “green LED” on node toggles according to commands.

3. Collector container logs show:

    ```markdown
    [DB] Inserted from node1: {...}
    [ML] Predicted LED=on ...
    ```

---

## 💡 4. Using the CLI

Use CLI commands via `run.sh`:

- Show most recent DB data:

```bash
./run.sh cli show
```

- Control actuators manually:

```bash
./run.sh cli set node1 on
./run.sh cli set node2 off
```

---

## 🌐 5. ML Pipeline

- Train a simple ML model in `/ml/train_model.ipynb` (e.g. threshold classifier).
- Export rules/params to `/ml/model_params.json`.
- Collector loads this on startup and takes autonomous LED decisions.

*(Demo model simply turns LED on if lux < 40, else off).*

---

## 🧪 6. Running End-to-End Demo

**Simulation Route:**

```bash
./run.sh backend    # start Docker infra
./run.sh sim        # build + launch Cooja
./run.sh cli show   # check DB contents
./run.sh cli set node1 on  # manual control
```

**Real Hardware Route (nRF52840):**

```bash
./run.sh backend
./run.sh flash   # build binaries for 3 nodes
# Then flash using nrfjprog/openocd:
nrfjprog --program node1.hex --chiperase --reset
```

After flashing, connect dongles → nodes behave like simulated ones, publishing lux values and listening for LED actuation via MQTT.

---

## 🛠 7. Compile for Hardware (detailed)

To compile firmware for the **nRF52840 boards**:

```bash
cd contiki_nodes
make node1 TARGET=nrf52840dk
make node2 TARGET=nrf52840dk
make node3 TARGET=nrf52840dk
```

To flash (example with `nrfjprog`):

```bash
nrfjprog --program node1.hex --reset
```

---

## 📌 Summary

- **Backend**: `./run.sh backend`
- **Simulated nodes**: `./run.sh sim`
- **Real hardware**: `./run.sh flash` + flash dongles
- **Inspect data**: `./run.sh cli show`
- **Control LEDs**: `./run.sh cli set node2 off`

With these unified commands, the project is reproducible both in Docker-only mode, in Cooja simulation, or with physical Nordic dongles.
