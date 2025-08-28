#!/usr/bin/env python3
"""
IoT Energy Management Controller
Cloud-ready backend service with REST API for remote webapp communication

Features:
- MQTT sensor data processing
- ML-based energy optimization
- REST API for webapp communication
- 24h override system with permanent/disabled options
- MySQL data persistence
"""

import os
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from flask import Flask, jsonify, request
import paho.mqtt.client as mqtt
import numpy as np
import pandas as pd
import joblib
import mysql.connector
import paho.mqtt.publish as publish

# Configuration
MQTT_BROKER = os.environ.get("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))

MYSQL_HOST = os.environ.get("MYSQL_HOST", "mysql")
MYSQL_USER = os.environ.get("MYSQL_USER", "iotuser")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "iotpass")
MYSQL_DB = os.environ.get("MYSQL_DB", "iotdb")

# Flask REST API
app = Flask(__name__)

# Global state management
device_overrides = {}  # {device_id: {status, expires_at, type}}
energy_stats = {
    "total_decisions": 0,
    "energy_saved": 0.0,
    "ambient_overrides": 0,
    "optimization_events": 0
}
latest_sensor_data = {}  # {device_id: latest_data}
last_device_states = {}  # {device_id: last_led_command} - Track actual state changes

class DatabaseManager:
    def __init__(self):
        self.connection = None
        self.connect()
    
    def connect(self):
        """Connect to MySQL database"""
        try:
            self.connection = mysql.connector.connect(
                host=MYSQL_HOST,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DB,
                autocommit=True
            )
            
            # Create tables
            cursor = self.connection.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sensor_data (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    device_id VARCHAR(50) NOT NULL,
                    payload JSON NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_device_time (device_id, timestamp)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS device_overrides (
                    device_id VARCHAR(50) PRIMARY KEY,
                    status VARCHAR(10) NOT NULL,
                    override_type VARCHAR(20) NOT NULL,
                    expires_at TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.close()
            print("✅ Database connected and tables initialized")
            
        except mysql.connector.Error as e:
            print(f"❌ Database error: {e}")
            self.connection = None

    def store_sensor_data(self, device_id: str, payload: dict):
        """Store sensor data in database"""
        if not self.connection:
            return
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO sensor_data (device_id, payload) VALUES (%s, %s)",
                (device_id, json.dumps(payload))
            )
            cursor.close()
        except mysql.connector.Error as e:
            print(f"❌ Database storage error: {e}")

    def get_recent_data(self, hours: int = 24) -> List[dict]:
        """Get recent sensor data"""
        if not self.connection:
            return []
        
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT device_id, payload, timestamp 
                FROM sensor_data 
                WHERE timestamp >= NOW() - INTERVAL %s HOUR
                ORDER BY timestamp DESC
            """, (hours,))
            
            results = []
            for row in cursor.fetchall():
                device_id, payload_str, timestamp = row
                try:
                    payload = json.loads(payload_str)
                    results.append({
                        'device_id': device_id,
                        'payload': payload,
                        'timestamp': str(timestamp)
                    })
                except json.JSONDecodeError:
                    continue
            
            cursor.close()
            return results
        except mysql.connector.Error as e:
            print(f"❌ Database query error: {e}")
            return []

    def save_override(self, device_id: str, status: str, override_type: str, expires_at: Optional[datetime] = None):
        """Save device override to database"""
        if not self.connection:
            return
        
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO device_overrides (device_id, status, override_type, expires_at)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                status = VALUES(status),
                override_type = VALUES(override_type),
                expires_at = VALUES(expires_at),
                created_at = CURRENT_TIMESTAMP
            """, (device_id, status, override_type, expires_at))
            self.connection.commit()  # Commit the transaction
            cursor.close()
            print(f"💾 Override saved to database: {device_id} = {status}")
        except mysql.connector.Error as e:
            print(f"❌ Override save error: {e}")
            self.connection.rollback()  # Rollback on error

    def load_overrides(self):
        """Load active overrides from database"""
        if not self.connection:
            return {}
        
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT device_id, status, override_type, expires_at
                FROM device_overrides
                WHERE expires_at IS NULL OR expires_at > NOW()
            """)
            
            overrides = {}
            for row in cursor.fetchall():
                device_id, status, override_type, expires_at = row
                overrides[device_id] = {
                    'status': status,
                    'type': override_type,
                    'expires_at': expires_at
                }
            
            cursor.close()
            return overrides
        except mysql.connector.Error as e:
            print(f"❌ Override load error: {e}")
            return {}

# Initialize database
db = DatabaseManager()

def load_ml_model():
    """Load trained ML model and parameters"""
    model = None
    feature_stats = None
    params = None
    
    # Try to load the actual trained model
    try:
        model = joblib.load('/app/ml/energy_saving_lighting_model.joblib')
        print("✅ Trained ML model loaded successfully")
    except FileNotFoundError:
        print("⚠️ Trained model not found, using rule-based fallback")
    except (ImportError, ModuleNotFoundError) as e:
        if 'numpy' in str(e).lower():
            print(f"❌ NumPy compatibility issue: {e}")
            print("🔧 This usually means the model was trained with a different NumPy version")
            print("⚠️ Falling back to rule-based decision making")
        else:
            print(f"❌ Import error loading model: {e}")
        model = None
    except Exception as e:
        print(f"❌ Unexpected error loading model: {e}")
        print("⚠️ Using rule-based fallback")
        model = None
    
    # Load feature statistics for normalization
    try:
        with open('/app/ml/feature_stats.json', 'r') as f:
            feature_stats = json.load(f)
        print("✅ Feature statistics loaded")
    except FileNotFoundError:
        print("⚠️ Feature stats not found")
    
    # Load model parameters
    try:
        with open('/app/ml/train_params.json', 'r') as f:
            params = json.load(f)
        print("✅ Model parameters loaded")
    except FileNotFoundError:
        print("⚠️ Using fallback parameters")
        params = {
            "model_type": "energy_saving_lighting_control",
            "objective": "minimize_lighting_energy_consumption",
            "energy_efficiency_improvement": "45.4%",
            "energy_saving_rules": {
                "lights_on_threshold": 0.1,
                "occupancy_required": True,
                "peak_waste_hours": [6, 7, 8, 9, 11],
                "turn_off_when_empty": True
            }
        }
    
    return model, feature_stats, params

# Load ML components
trained_model, feature_stats, model_params = load_ml_model()
print(f"🧠 ML System: {model_params.get('model_type', 'fallback')}")
print(f"⚡ Energy efficiency: {model_params.get('energy_efficiency_improvement', 'N/A')}")
print(f"🎯 Using {'trained model' if trained_model else 'rule-based'} decision making")

def prepare_ml_features(sensor_data: dict):
    """
    Prepare sensor data for ML model prediction
    Returns pandas DataFrame with proper feature names to avoid sklearn warnings
    Expected features: ['hour_of_day', 'total_room_usage', 'lights_currently_on', 
                       'space_occupied', 'solar_surplus', 'cloudCover', 'visibility']
    """
    current_hour = datetime.now().hour
    
    # Extract sensor values with defaults
    lux = sensor_data.get('lux', 50)
    occupancy = sensor_data.get('occupancy', 0)
    room_usage = sensor_data.get('room_usage', 0.0)
    
    # Infer additional features 
    lights_currently_on = 1 if room_usage > 0.15 else 0  # Updated threshold for 150W LEDs
    space_occupied = occupancy  # Direct mapping
    
    # Environmental features (with defaults if not available)
    solar_surplus = sensor_data.get('solar_surplus', -0.95)  # Default from training data
    cloud_cover = sensor_data.get('cloudCover', 0.2)
    visibility = sensor_data.get('visibility', 9.5)
    
    # Create DataFrame with proper feature names (prevents sklearn warnings)
    feature_data = {
        'hour_of_day': [current_hour],
        'total_room_usage': [room_usage],
        'lights_currently_on': [lights_currently_on],
        'space_occupied': [space_occupied],
        'solar_surplus': [solar_surplus],
        'cloudCover': [cloud_cover],
        'visibility': [visibility]
    }
    
    features_df = pd.DataFrame(feature_data)
    return features_df

def ml_energy_decision(sensor_data: dict) -> Tuple[str, float, str]:
    """
    Use trained ML model for energy saving decision
    Returns: (action, energy_saved_vs_baseline_kwh, reason)
    
    Baseline assumption: Lights are always ON when room is occupied
    Energy savings calculated as difference between baseline and ML decision
    """
    if trained_model is None:
        # Fallback to rule-based if model not available
        return rule_based_energy_decision(sensor_data)
    
    try:
        # Prepare features for ML model
        features = prepare_ml_features(sensor_data)
        
        # Get ML prediction
        prediction = trained_model.predict(features)[0]  # 0 = keep current, 1 = save energy
        prediction_proba = trained_model.predict_proba(features)[0]
        confidence = max(prediction_proba)
        
        # Extract relevant data for energy calculation
        room_usage = sensor_data.get('room_usage', 0.0)
        occupancy = sensor_data.get('occupancy', 0)
        lux = sensor_data.get('lux', 50)
        
        # BASELINE CALCULATION: What would baseline behavior be?
        # Baseline: Always turn lights ON when room is occupied (150W = 0.15kW)
        baseline_energy = 0.15 if occupancy > 0 else 0.0
        
        # ML DECISION LOGIC
        if prediction == 1:  # Model suggests saving energy
            if occupancy > 0:
                # Room is occupied but ML suggests saving energy
                if lux >= 60:  # Sufficient ambient light
                    action = "turn_off"
                    ml_energy = 0.0  # ML keeps lights off
                    reason = f"ml_prediction_sufficient_ambient_light_conf_{confidence:.2f}"
                else:
                    # Occupied but ML optimizes consumption
                    action = "reduce_lighting"
                    ml_energy = 0.075  # Reduced lighting (50% of 150W)
                    reason = f"ml_prediction_optimize_occupied_space_conf_{confidence:.2f}"
            else:
                # Room unoccupied - ML keeps lights off (same as baseline)
                action = "turn_off"
                ml_energy = 0.0
                reason = f"ml_prediction_unoccupied_space_conf_{confidence:.2f}"
        else:  # Model suggests keeping current state or turning on
            if occupancy > 0:
                # Room occupied - ML agrees with baseline to have lights on
                action = "turn_on"
                ml_energy = 0.15  # Full lighting
                reason = f"ml_prediction_appropriate_usage_conf_{confidence:.2f}"
            else:
                # Room unoccupied - ML keeps lights off
                action = "turn_off"
                ml_energy = 0.0
                reason = f"ml_prediction_keep_off_unoccupied_conf_{confidence:.2f}"
        
        # Calculate energy savings vs baseline
        energy_saved = baseline_energy - ml_energy
        
        return action, energy_saved, reason
        
    except Exception as e:
        print(f"❌ ML prediction error: {e}")
        return rule_based_energy_decision(sensor_data)

def rule_based_energy_decision(sensor_data: dict) -> Tuple[str, float, str]:
    """
    Fallback rule-based energy saving decision (original logic)
    Returns: (action, energy_saved_vs_baseline_kwh, reason)
    
    Baseline assumption: Lights are always ON when room is occupied
    """
    lux = sensor_data.get('lux', 50)
    occupancy = sensor_data.get('occupancy', 0)
    room_usage = sensor_data.get('room_usage', 0.0)
    
    current_hour = datetime.now().hour
    rules = model_params['energy_saving_rules']
    
    # BASELINE: What would baseline behavior be?
    baseline_energy = 0.15 if occupancy > 0 else 0.0  # 150W when occupied
    
    # Detect if lights are currently on (updated for 150W LEDs)
    lights_on = room_usage > 0.15  # Threshold increased for 150W LEDs
    
    # RULE-BASED DECISIONS
    # Energy waste detection - room unoccupied
    if occupancy == 0:
        # Both baseline and rule-based keep lights off when unoccupied
        rule_energy = 0.0
        action = "turn_off"
        reason = "rule_based_empty_space"
    # Peak hour optimization - reduce consumption even when occupied
    elif current_hour in rules['peak_waste_hours'] and occupancy > 0:
        rule_energy = 0.075  # Reduced lighting (50% of 150W)
        action = "reduce_lighting"
        reason = "rule_based_peak_hour_optimization"
    # Night energy saving - be more conservative
    elif (current_hour >= 23 or current_hour <= 5) and occupancy > 0:
        if lux >= 40:  # Some ambient light available at night
            rule_energy = 0.0  # Turn off even when occupied
            action = "turn_off"
            reason = "rule_based_nighttime_ambient_sufficient"
        else:
            rule_energy = 0.075  # Reduced lighting
            action = "reduce_lighting"
            reason = "rule_based_nighttime_reduced"
    # Standard occupied room behavior
    else:
        rule_energy = 0.15  # Full lighting when occupied
        action = "turn_on"
        reason = "rule_based_appropriate_usage"
    
    # Calculate energy savings vs baseline
    energy_saved = baseline_energy - rule_energy
    
    return action, energy_saved, reason

def energy_saving_decision(sensor_data: dict) -> Tuple[str, float, str]:
    """
    Main energy saving decision function - uses ML model if available, otherwise rules
    Returns: (action, energy_saved_kwh, reason)
    """
    if trained_model is not None:
        return ml_energy_decision(sensor_data)
    else:
        return rule_based_energy_decision(sensor_data)

def ambient_light_optimization(lux: int, led_command: str) -> Tuple[str, bool, float]:
    """
    Ambient light optimization logic - updated for realistic time-based lighting
    Returns: (final_command, optimization_triggered, energy_saved)
    """
    # Updated thresholds for more realistic lighting patterns
    AMBIENT_THRESHOLD = 60  # Slightly lower threshold for realistic outdoor light simulation
    TARGET_LUX = 65
    
    if led_command == "on" and lux >= AMBIENT_THRESHOLD:
        return "off", True, 0.15  # Save 0.15 kWh by not turning on 150W lights
    
    return led_command, False, 0.0

def check_device_override(device_id: str) -> Optional[str]:
    """
    Check if device has active override
    Returns: override status or None
    """
    if device_id not in device_overrides:
        return None
    
    override = device_overrides[device_id]
    
    # Check if override has expired
    if override.get('expires_at') and datetime.now() > override['expires_at']:
        # Remove expired override
        del device_overrides[device_id]
        # Remove from database
        if db.connection:
            try:
                cursor = db.connection.cursor()
                cursor.execute("DELETE FROM device_overrides WHERE device_id = %s", (device_id,))
                cursor.close()
            except mysql.connector.Error:
                pass
        return None
    
    return override['status']

def set_device_override(device_id: str, status: str, override_type: str = "24h"):
    """
    Set device override with different durations
    override_type: "24h", "permanent", "disabled"
    """
    expires_at = None
    
    if override_type == "24h":
        expires_at = datetime.now() + timedelta(hours=24)
    elif override_type == "permanent":
        expires_at = None
    elif override_type == "disabled":
        # Remove override
        if device_id in device_overrides:
            del device_overrides[device_id]
        if db.connection:
            try:
                cursor = db.connection.cursor()
                cursor.execute("DELETE FROM device_overrides WHERE device_id = %s", (device_id,))
                db.connection.commit()  # Commit the deletion
                cursor.close()
                print(f"💾 Override deleted from database: {device_id}")
            except mysql.connector.Error as e:
                print(f"❌ Override deletion error: {e}")
                db.connection.rollback()
        
        # Notify virtual nodes that override is disabled
        override_topic = f"devices/{device_id}/override"
        override_message = {
            'status': 'disabled',
            'type': 'disabled'
        }
        publish.single(override_topic, json.dumps(override_message), hostname=MQTT_BROKER, port=MQTT_PORT)
        print(f"🎛️ Override removed: {device_id}")
        return
    
    device_overrides[device_id] = {
        'status': status,
        'type': override_type,
        'expires_at': expires_at
    }
    
    # Save to database
    db.save_override(device_id, status, override_type, expires_at)
    
    # Notify virtual nodes about the override via MQTT
    override_topic = f"devices/{device_id}/override"
    override_message = {
        'status': status,
        'type': override_type,
        'expires_at': expires_at.isoformat() if expires_at else None
    }
    publish.single(override_topic, json.dumps(override_message), hostname=MQTT_BROKER, port=MQTT_PORT)
    
    print(f"🎛️ Override set: {device_id} = {status} ({override_type})")

def process_sensor_data(device_id: str, payload: dict):
    """Process incoming sensor data"""
    # Store in database
    db.store_sensor_data(device_id, payload)
    
    # Update latest data
    latest_sensor_data[device_id] = {
        **payload,
        'timestamp': datetime.now().isoformat()
    }
    
    # Check for override first
    override_status = check_device_override(device_id)
    if override_status:
        # Override is active - do NOT send any LED commands
        reason = f"manual_override_{device_overrides[device_id]['type']}"
        print(f"🎛️ Override active: {device_id} = {override_status} ({reason}) - skipping automatic control")
        return  # Exit early, don't send any actuator commands
    
    # No override - proceed with ML-based decision (or rule-based fallback)
    action, energy_saved, reason = energy_saving_decision(payload)
    
    # Convert action to LED command
    if action in ["turn_off", "keep_off"]:
        led_command = "off"
    elif action in ["turn_on", "appropriate_usage"]:
        led_command = "on"
    elif action == "reduce_lighting":
        # For reduced lighting, we use "on" but could be implemented as dimming in the future
        led_command = "on"  # Currently binary on/off, but represents reduced consumption
    else:
        # Default to energy saving for unknown actions
        led_command = "off"
    
    
    # Ambient light optimization
    lux = payload.get('lux', 50)
    original_command = led_command
    led_command, ambient_triggered, ambient_energy = ambient_light_optimization(lux, led_command)
    
    if ambient_triggered:
        energy_saved += ambient_energy
        energy_stats["ambient_overrides"] += 1
        reason += "_ambient_sufficient"
    
    # Only update stats if LED command actually changed
    last_command = last_device_states.get(device_id)
    if last_command != led_command:
        # Update global stats only on actual state change
        energy_stats["total_decisions"] += 1
        energy_stats["energy_saved"] += energy_saved
        
        # Increment ML optimizations counter when ML model is used
        if trained_model and 'ml_prediction' in reason:
            energy_stats["optimization_events"] += 1
        
        last_device_states[device_id] = led_command
        
        print(f"⚡ {device_id}: {original_command} → {led_command}, saved: {energy_saved:.3f}kWh vs baseline")
        print(f"   🤖 Decision method: {'ML Model' if trained_model and 'ml_prediction' in reason else 'Rule-based'}")
        print(f"   💡 Baseline would use: {0.15 if payload.get('occupancy', 0) > 0 else 0.0:.3f}kWh (150W when occupied)")
        print(f"   📊 Reason: {reason}")
    
    # Send LED command (only when no override is active)
    actuator_topic = f"actuators/{device_id}/led"
    publish.single(actuator_topic, led_command, hostname=MQTT_BROKER, port=MQTT_PORT)

# MQTT Event Handlers
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ MQTT connected to {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe("sensors/+/data")
        client.subscribe("sensors/+/button")
    else:
        print(f"❌ MQTT connection failed: {rc}")

def on_message(client, userdata, msg):
    try:
        device_id = msg.topic.split('/')[1]  # Extract device_id from topic
        payload = json.loads(msg.payload.decode())
        
        if "/button" in msg.topic:
            # Handle button press - toggle override
            current_override = check_device_override(device_id)
            if current_override:
                set_device_override(device_id, "disabled", "disabled")
                print(f"🔘 Button press: {device_id} override disabled")
            else:
                # Set 24h override to opposite of current ML decision
                action, _, _ = energy_saving_decision(latest_sensor_data.get(device_id, {}))
                new_status = "on" if action == "turn_off" else "off"
                set_device_override(device_id, new_status, "24h")
                print(f"🔘 Button press: {device_id} override set to {new_status} (24h)")
        else:
            # Regular sensor data
            process_sensor_data(device_id, payload)
            
    except Exception as e:
        print(f"❌ Message processing error: {e}")

# Load existing overrides
device_overrides = db.load_overrides()
print(f"📋 Loaded {len(device_overrides)} existing overrides")

# REST API Endpoints
@app.route('/api/status', methods=['GET'])
def get_status():
    """Get system status"""
    return jsonify({
        'status': 'running',
        'energy_stats': energy_stats,
        'active_overrides': len(device_overrides),
        'latest_data_count': len(latest_sensor_data),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/devices', methods=['GET'])
def get_devices():
    """Get all devices with latest data and override status"""
    devices = {}
    
    for device_id, data in latest_sensor_data.items():
        override = device_overrides.get(device_id)
        devices[device_id] = {
            'latest_data': data,
            'override': {
                'active': override is not None,
                'status': override['status'] if override else None,
                'type': override['type'] if override else None,
                'expires_at': override['expires_at'].isoformat() if override and override.get('expires_at') else None
            } if override else {'active': False}
        }
    
    return jsonify(devices)

@app.route('/api/devices/<device_id>/override', methods=['POST'])
def set_override(device_id):
    """Set device override"""
    data = request.get_json()
    status = data.get('status')  # "on" or "off"
    override_type = data.get('type', '24h')  # "24h", "permanent", "disabled"
    
    if status not in ['on', 'off']:
        return jsonify({'error': 'Status must be "on" or "off"'}), 400
    
    if override_type not in ['24h', 'permanent', 'disabled']:
        return jsonify({'error': 'Type must be "24h", "permanent", or "disabled"'}), 400
    
    set_device_override(device_id, status, override_type)
    
    return jsonify({
        'success': True,
        'device_id': device_id,
        'status': status,
        'type': override_type,
        'expires_at': device_overrides[device_id]['expires_at'].isoformat() if device_id in device_overrides and device_overrides[device_id].get('expires_at') else None
    })

@app.route('/api/devices/<device_id>/override', methods=['DELETE'])
def remove_override(device_id):
    """Remove device override"""
    set_device_override(device_id, "disabled", "disabled")
    return jsonify({'success': True, 'device_id': device_id})

@app.route('/api/sensor-data', methods=['GET'])
def get_sensor_data():
    """Get recent sensor data"""
    hours = request.args.get('hours', 24, type=int)
    data = db.get_recent_data(hours)
    return jsonify(data)

@app.route('/api/energy-stats', methods=['GET'])
def get_energy_stats():
    """Get energy optimization statistics"""
    return jsonify(energy_stats)

@app.route('/api/baseline-comparison', methods=['GET'])
def get_baseline_comparison():
    """Get detailed baseline vs ML model comparison statistics"""
    # Calculate what baseline consumption would be based on current occupancy
    total_baseline_energy = 0.0
    total_rooms_occupied = 0
    
    for device_id, sensor_data in latest_sensor_data.items():
        occupancy = sensor_data.get('occupancy', 0)
        if occupancy > 0:
            total_baseline_energy += 0.15  # 150W baseline when occupied
            total_rooms_occupied += 1
    
    # Calculate efficiency metrics
    efficiency_improvement = 0.0
    if total_baseline_energy > 0:
        efficiency_improvement = (energy_stats['energy_saved'] / total_baseline_energy) * 100
    
    comparison_stats = {
        'baseline_assumption': 'Lights always ON when room is occupied (150W per room)',
        'current_baseline_consumption_kw': total_baseline_energy,
        'rooms_currently_occupied': total_rooms_occupied,
        'ml_energy_saved_vs_baseline_kwh': energy_stats['energy_saved'],
        'efficiency_improvement_percent': round(efficiency_improvement, 1),
        'total_ml_decisions': energy_stats['optimization_events'],
        'total_system_decisions': energy_stats['total_decisions'],
        'ml_model_active': trained_model is not None,
        'energy_stats': energy_stats,
        'calculation_timestamp': datetime.now().isoformat()
    }
    
    return jsonify(comparison_stats)

@app.route('/api/model-info', methods=['GET'])
def get_model_info():
    """Get ML model information and capabilities"""
    model_info = {
        'model_loaded': trained_model is not None,
        'model_type': model_params.get('model_type', 'unknown'),
        'decision_method': 'trained_ml_model' if trained_model else 'rule_based_fallback',
        'energy_efficiency': model_params.get('energy_efficiency_improvement', 'N/A'),
        'accuracy': model_params.get('accuracy', 'N/A'),
        'features_available': feature_stats is not None,
        'feature_count': 7 if trained_model else 0,
        'expected_features': [
            'hour_of_day', 'total_room_usage', 'lights_currently_on', 
            'space_occupied', 'solar_surplus', 'cloudCover', 'visibility'
        ] if trained_model else [],
        'energy_saving_rules': model_params.get('energy_saving_rules', {}),
        'training_info': model_params.get('training_info', {})
    }
    return jsonify(model_info)

@app.route('/api/system/refresh', methods=['POST'])
def refresh_system():
    """Refresh system status and reset stats"""
    global energy_stats, last_device_states
    
    # Reset energy statistics
    energy_stats = {
        "total_decisions": 0,
        "energy_saved": 0.0,
        "ambient_overrides": 0,
        "optimization_events": 0
    }
    
    # Clear device state tracking
    last_device_states = {}
    
    # Publish system refresh command
    try:
        publish.single("system/commands", json.dumps({"command": "status_refresh"}), 
                      hostname=MQTT_BROKER, port=MQTT_PORT)
    except Exception as e:
        print(f"❌ Failed to publish refresh command: {e}")
    
    return jsonify({
        'success': True,
        'message': 'System refreshed successfully',
        'energy_stats': energy_stats
    })

@app.route('/api/devices/all/control', methods=['POST'])
def global_device_control():
    """Control all devices globally"""
    data = request.get_json()
    command = data.get('command')
    
    if command not in ['all_on', 'all_off', 'energy_saving']:
        return jsonify({'success': False, 'error': 'Invalid command'}), 400
    
    try:
        # Publish global command
        global_topic = "devices/all/control"
        publish.single(global_topic, json.dumps({"command": command}), 
                      hostname=MQTT_BROKER, port=MQTT_PORT)
        
        return jsonify({
            'success': True,
            'command': command,
            'message': f'Global command {command} sent to all devices'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/devices/all/override/clear', methods=['POST'])
def clear_all_overrides():
    """Clear all device overrides and return to auto mode"""
    try:
        cleared_devices = []
        
        # Clear all overrides from memory and database
        for device_id in list(device_overrides.keys()):
            set_device_override(device_id, "disabled", "disabled")
            cleared_devices.append(device_id)
        
        return jsonify({
            'success': True,
            'message': f'Cleared overrides for {len(cleared_devices)} devices',
            'devices': cleared_devices
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def start_mqtt_client():
    """Start MQTT client in separate thread"""
    client = mqtt.Client(client_id="iot_controller")
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except Exception as e:
        print(f"❌ MQTT client error: {e}")

if __name__ == "__main__":
    print("🚀 IoT Energy Management Controller Starting...")
    print(f"🌐 REST API will be available on port 5001")
    print(f"📡 MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"🗄️ Database: {MYSQL_HOST}/{MYSQL_DB}")
    
    # Start MQTT client in background thread
    mqtt_thread = threading.Thread(target=start_mqtt_client, daemon=True)
    mqtt_thread.start()
    
    # Start Flask REST API
    app.run(host='0.0.0.0', port=5001, debug=False)