# IoT Energy Management System

## Cloud-ready Smart Home Energy Management IoT System

> Modern microservices architecture with REST API communication, 24h override system, and ML-powered energy optimization.

---

## 🏗️ Architecture Overview

This is a **distributed IoT system** designed for cloud deployment with clean service separation:

- **Controller Backend** (REST API on port 5001) → handles MQTT processing, ML decisions, database management
- **Web Frontend** (port 5000) → user interface communicating with controller via REST API
- **24h Override System** → temporary/permanent/disabled device control modes
- **MQTT Processing** → real-time sensor data from IoT nodes
- **ML Energy Optimization** → intelligent lighting decisions based on occupancy/ambient light

**Key Features:**

- 🌐 **Cloud-ready architecture** with REST API communication
- 🔧 **24h override system** with auto-expiry, permanent, and disabled modes  
- 🤖 **ML-powered energy optimization** for autonomous device control
- 🐳 **Docker containerization** with service isolation
- 📊 **Real-time monitoring** with WebSocket updates
- 🎛️ **Web dashboard** for device control and analytics

---

## 📂 Project Structure

```markdown
IoT-Project/
│
├── run.sh                    # 🚀 MAIN ENTRY POINT - unified management script
├── docker-compose.yml        # Container orchestration
├── README.md                # This documentation
│
├── controller/              # 🎛️ Backend REST API service
│   ├── controller.py        # Main Flask API + MQTT processing
│   ├── Dockerfile          # Controller container
│   └── requirements.txt    # Python dependencies
│
├── webapp/                  # 🌐 Frontend web application
│   ├── app.py              # Flask web UI (REST API client)
│   ├── Dockerfile          # Webapp container  
│   ├── requirements.txt    # Web app dependencies
│   └── static/             # CSS, JS, images
│       └── templates/       # HTML templates
│
├── config/                  # 📋 Configuration files
│   ├── devices.json        # Device definitions
│   └── mosquitto.conf      # MQTT broker config
│
├── contiki_nodes/          # 🎭 IoT node firmware (Contiki-NG)
│   ├── node1.c, node2.c, node3.c
│   └── project-conf.h      # Node configuration
│
├── ml/                     # 🤖 Machine learning pipeline
│   ├── train_model.ipynb   # Complete ML training notebook
│   └── train_params.json   # Trained model parameters
│
└── cli/                    # 🖥️ Command line interface (legacy)
    ├── control.py          # CLI commands
    └── requirements.txt    # CLI dependencies
```

---

## 🚀 Quick Start Guide

### 1. Initialize System

```bash
# First time setup - installs all dependencies
./run.sh init

# Log out and back in for Docker permissions
logout && login
```

### 2. Start Complete System

```bash
# Start everything: services + simulated IoT nodes
./run.sh start

# 🌍 Access the system:
# Web Dashboard:    http://localhost:5000
# Device Control:   http://localhost:5000/control  
# Analytics:        http://localhost:5000/analytics
# Controller API:   http://localhost:5001/api/status
```

### 3. Monitor System

```bash
# Check system status
./run.sh status

# View live logs
./run.sh logs

# View specific service logs
./run.sh logs controller
./run.sh logs webapp
```

### 4. Stop System

```bash
./run.sh stop
```

---

## 🎮 Simulation Mode (Cooja)

For **hardware-in-the-loop testing** with Contiki-NG nodes:

```bash
# Start with Cooja simulation environment
./run.sh sim

# This will:
# 1. Build Contiki-NG firmware for nodes
# 2. Start backend services (MQTT, MySQL, Controller)
# 3. Launch Cooja simulator
# 4. Start web interface

# In Cooja:
# 1. Create new simulation
# 2. Add border router (IPv6: fd00::1)
# 3. Add 3 nodes using compiled .cooja files
# 4. Start simulation
# 5. Monitor web dashboard: http://localhost:5000
```

---

## 🌐 REST API Reference

The **Controller** exposes a comprehensive REST API for cloud integration:

### Device Management

```bash
# Get all devices and their status
GET http://localhost:5001/api/devices

# Get recent sensor data  
GET http://localhost:5001/api/sensor-data

# System health check
GET http://localhost:5001/api/status
```

### Override System (24h Auto-Expiry)

```bash
# Set 24h override (auto-expires after 24 hours)
POST http://localhost:5001/api/devices/node1/override
{
  "status": "on",
  "type": "24h"
}

# Set permanent override (never expires)
POST http://localhost:5001/api/devices/node1/override  
{
  "status": "off",
  "type": "permanent"
}

# Disable override (return to ML control)
POST http://localhost:5001/api/devices/node1/override
{
  "status": "off", 
  "type": "disabled"
}

# Remove override completely
DELETE http://localhost:5001/api/devices/node1/override
```

---

## 🖥️ Command Line Interface

Use the CLI for quick operations:

```bash
# Show recent sensor data
./run.sh cli show

# Show device status
./run.sh cli devices

# Set device override
./run.sh cli override node1 on 24h
./run.sh cli override node2 off permanent  
./run.sh cli override node3 off disabled
```

---

## 🤖 Machine Learning Pipeline

**Intelligent Energy Management** with trained Random Forest model:

- **Dataset**: Smart Home Energy Management (10,000 samples)
- **Algorithm**: Random Forest Classifier (95.23% accuracy)
- **Features**: Light level, occupancy, time of day, temperature, room usage
- **Optimization**: Energy-efficient lighting with user comfort
- **Deployment**: Lightweight inference in controller service

**Energy Optimization Logic:**

- ✅ LED ON: Room occupied + low ambient light + energy budget available
- ❌ LED OFF: Room empty OR high ambient light OR energy budget exceeded
- 🕐 **24h Override System**: Temporary manual control with auto-expiry

The ML model runs continuously in the controller, making decisions every 5 seconds based on real-time sensor data.

---

## 🐳 Docker Architecture

**Service Separation** for cloud deployment:

```yaml
services:
  controller:    # Backend REST API + MQTT processing + ML
    ports: ["5001:5001"]
    networks: [iot-network]
    
  webapp:        # Frontend web UI (REST API client)  
    ports: ["5000:5000"]
    networks: [iot-network]
    depends_on: [controller]
    
  mosquitto:     # MQTT broker
    ports: ["1883:1883"]
    
  mysql:         # Database
    ports: ["3306:3306"]
```

**Benefits:**

- 🌐 **Cloud-ready**: Web app can be deployed remotely, communicates via REST API
- 🔄 **Scalable**: Controller can handle multiple web app instances
- 🛡️ **Secure**: Network isolation between services
- 📊 **Observable**: Separate logging and monitoring per service

---

## 🔧 Development & Testing

### Build Containers

```bash
./run.sh build
```

### Development Mode

```bash
# Start only backend services
docker compose up -d mosquitto mysql controller

# Run webapp locally for development
cd webapp
python app.py
```

### Testing Commands

```bash
# Test controller API
curl http://localhost:5001/api/status

# Test device override
curl -X POST http://localhost:5001/api/devices/node1/override \
     -H "Content-Type: application/json" \
     -d '{"status":"on","type":"24h"}'

# Test sensor data endpoint
curl http://localhost:5001/api/sensor-data | jq '.'
```

### Hardware Deployment (nRF52840)

```bash
# Build firmware for Nordic boards
cd contiki_nodes
make node1 TARGET=nrf52840dk
make node2 TARGET=nrf52840dk  
make node3 TARGET=nrf52840dk

# Flash with nrfjprog
nrfjprog --program node1.hex --chiperase --reset
```

---

## 📋 System Status & Monitoring

**Real-time Monitoring:**

- 📊 **Web Dashboard**: Device status, sensor readings, energy analytics
- 🔍 **System Logs**: `./run.sh logs` for debugging
- 💡 **Device Control**: Override system with 24h auto-expiry
- 📈 **Analytics**: Energy consumption trends and ML decision history

**Health Checks:**

- Controller API: `http://localhost:5001/api/status`
- Web App: `http://localhost:5000/api/status`  
- MQTT Broker: Port 1883 connectivity
- Database: MySQL on port 3306

---

## 🎯 Use Cases

1. **Smart Home Energy Management**
   - Automatic lighting control based on occupancy
   - Energy optimization with user comfort
   - 24h manual override for special events

2. **Cloud IoT Platform**
   - REST API for remote device management
   - Scalable microservices architecture
   - Real-time monitoring and analytics

3. **Research & Development**
   - ML model training and evaluation
   - IoT protocol testing with Contiki-NG
   - Edge computing optimization

---

## 🚀 Next Steps

1. **Start the system**: `./run.sh start`
2. **Open web dashboard**: <http://localhost:5000>
3. **Monitor device control**: <http://localhost:5000/control>
4. **View analytics**: <http://localhost:5000/analytics>
5. **Test CLI**: `./run.sh cli devices`

---

## 📝 Quick Reference

```bash
# Essential Commands
./run.sh init     # First-time setup
./run.sh start    # Start complete system  
./run.sh stop     # Stop all services
./run.sh status   # Check system health
./run.sh logs     # View system logs

# Simulation & Development  
./run.sh sim      # Cooja simulation mode
./run.sh build    # Build containers
./run.sh cli      # Command line interface

# Web Access Points
http://localhost:5000           # Main dashboard
http://localhost:5000/control   # Device control
http://localhost:5000/analytics # Energy analytics
http://localhost:5001/api       # Controller REST API
```

---

**🌐 Web Interface: <http://localhost:5000>**

**⚡ Built with:** Python, Flask, Docker, MQTT, MySQL, Contiki-NG, Machine Learning
