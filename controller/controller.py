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
import warnings
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from flask import Flask, jsonify, request
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
import mysql.connector
import joblib
import pandas as pd
import numpy as np

# Configuration
MQTT_BROKER = os.environ.get("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))

MYSQL_HOST = os.environ.get("MYSQL_HOST", "mysql")
MYSQL_USER = os.environ.get("MYSQL_USER", "iotuser")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "iotpass")
MYSQL_DB = os.environ.get("MYSQL_DB", "iotdb")

# Configure logging - minimize HTTP logs, maximize error tracking
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Get logger for this module
logger = logging.getLogger(__name__)

# Suppress Flask HTTP request logging (werkzeug)
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.ERROR)  # Only show errors, not every HTTP request

# Create Flask app with minimal logging
app = Flask(__name__)
app.logger.setLevel(logging.ERROR)  # Suppress Flask info logs

# Critical operation counter for monitoring
critical_ops = {
    "db_errors": 0,
    "mqtt_errors": 0,
    "ml_errors": 0,
    "api_errors": 0,
    "total_restarts": 0
}

def log_critical_error(operation: str, error: Exception, context: str = ""):
    """Log critical errors that might cause crashes"""
    critical_ops[f"{operation}_errors"] = critical_ops.get(f"{operation}_errors", 0) + 1
    logger.error(f"💥 CRITICAL {operation.upper()} ERROR: {error}")
    if context:
        logger.error(f"   📍 Context: {context}")
    logger.error(f"   📊 Error count for {operation}: {critical_ops.get(f'{operation}_errors', 0)}")
    
    # Log stack trace for debugging
    import traceback
    logger.error(f"   📚 Stack trace:\n{traceback.format_exc()}")

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.warning(f"🔄 Received signal {signum}, shutting down gracefully...")
    critical_ops["total_restarts"] += 1
    logger.info(f"📊 Total restarts: {critical_ops['total_restarts']}")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Global state management
device_overrides = {}  # {device_id: {status, expires_at, type}}
latest_sensor_data = {}  # {device_id: latest_data}
last_device_states = {}  # {device_id: last_led_command} - Track actual state changes

class DatabaseManager:
    def __init__(self):
        self.connection = None
        self.connection_attempts = 0
        self.max_retries = 3
        self._connection_lock = threading.Lock()  # Thread safety for connection operations
        self.connect()
    
    def is_connected(self):
        """Check if database connection is alive"""
        with self._connection_lock:
            if not self.connection:
                return False
            try:
                # Simple test query instead of ping to avoid issues
                cursor = self.connection.cursor(buffered=True)
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                return True
            except (mysql.connector.Error, AttributeError, ReferenceError):
                # Connection is dead or corrupted
                self._close_connection()
                return False
    
    def _close_connection(self):
        """Safely close existing connection"""
        if self.connection:
            try:
                if self.connection.is_connected():
                    self.connection.close()
            except:
                pass  # Ignore errors during close
            finally:
                self.connection = None
    
    def ensure_connection(self):
        """Ensure database connection is alive, reconnect if needed"""
        if not self.is_connected():
            logger.warning("🔄 Database connection lost, attempting reconnection...")
            self.connect()
        return self.connection is not None
    
    def connect(self):
        """Connect to MySQL database with retry logic"""
        with self._connection_lock:
            self.connection_attempts += 1
            
            try:
                logger.info(f"🔗 Attempting database connection to {MYSQL_HOST}:{MYSQL_DB} (attempt {self.connection_attempts})")
                
                # Close existing connection if any
                self._close_connection()
                
                # Create new connection with conservative settings
                self.connection = mysql.connector.connect(
                    host=MYSQL_HOST,
                    user=MYSQL_USER,
                    password=MYSQL_PASSWORD,
                    database=MYSQL_DB,
                    connect_timeout=30,
                    autocommit=True,  # Enable autocommit to prevent transaction issues
                    buffered=True,    # Use buffered connections by default
                    raise_on_warnings=False,
                    sql_mode='',
                    use_unicode=True,
                    charset='utf8mb4'  # Better unicode support
                )
                
                # Test connection with simple query
                if self.connection and self.connection.is_connected():
                    cursor = self.connection.cursor(buffered=True)
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    cursor.close()
                    
                    # Create tables after confirming connection works
                    self._create_tables()
                    
                    # Verify connection is still good after table creation
                    if self.connection and self.connection.is_connected():
                        logger.info("✅ Database connected and tables initialized")
                        self.connection_attempts = 0  # Reset counter on success
                    else:
                        logger.error("❌ Connection lost during table creation")
                        raise mysql.connector.Error("Connection lost during table creation")
                else:
                    logger.error("❌ Failed to establish valid connection")
                    raise mysql.connector.Error("Failed to establish valid connection")
                
            except mysql.connector.Error as e:
                log_critical_error("db", e, f"Failed to connect to {MYSQL_HOST}:{MYSQL_DB} (attempt {self.connection_attempts})")
                self._close_connection()
                
                # Exponential backoff for retries
                if self.connection_attempts < self.max_retries:
                    wait_time = min(2 ** self.connection_attempts, 30)  # Max 30 seconds
                    logger.warning(f"⏳ Retrying database connection in {wait_time} seconds...")
                    time.sleep(wait_time)
                    return self.connect()
                else:
                    logger.error("💥 Database connection failed after max retries")
                    
            except Exception as e:
                log_critical_error("db", e, "Unexpected database connection error")
                self._close_connection()

    def _create_tables(self):
        """Create database tables with error handling"""
        if not self.connection:
            return
            
        cursor = None
        try:
            cursor = self.connection.cursor(buffered=True)
            
            # Sensor data table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sensor_data (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    device_id VARCHAR(50) NOT NULL,
                    payload JSON NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_device_time (device_id, timestamp)
                )
            """)
            
            # Device overrides table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS device_overrides (
                    device_id VARCHAR(50) PRIMARY KEY,
                    status VARCHAR(10) NOT NULL,
                    override_type VARCHAR(20) NOT NULL,
                    expires_at TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Energy stats table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS energy_stats (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    total_decisions INT DEFAULT 0,
                    energy_saved DECIMAL(10,3) DEFAULT 0.000,
                    ambient_overrides INT DEFAULT 0,
                    optimization_events INT DEFAULT 0,
                    baseline_energy DECIMAL(10,3) DEFAULT 0.000,
                    ml_energy DECIMAL(10,3) DEFAULT 0.000,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Ensure there's always one row for energy stats
            cursor.execute("""
                INSERT IGNORE INTO energy_stats (id, total_decisions, energy_saved, ambient_overrides, optimization_events, baseline_energy, ml_energy) 
                VALUES (1, 0, 0.000, 0, 0, 0.000, 0.000)
            """)
            
            # Since autocommit=True, no need for explicit commit
            logger.info("📊 Database tables created/verified successfully")
            
        except mysql.connector.Error as e:
            log_critical_error("db", e, "Failed to create database tables")
            # Reset connection on table creation failure to prevent corruption
            self._close_connection()
        except Exception as e:
            log_critical_error("db", e, "Unexpected error creating database tables")
            # Reset connection on any error to prevent memory corruption
            self._close_connection()
        finally:
            # Always ensure cursor is properly closed
            if cursor:
                try:
                    cursor.close()
                except:
                    pass  # Ignore cursor close errors

    def store_sensor_data(self, device_id: str, payload: dict):
        """Store sensor data in database with automatic reconnection"""
        if not self.ensure_connection():
            logger.warning("📊 Cannot store sensor data - database connection unavailable after reconnection attempts")
            return
        
        retry_count = 0
        max_retries = 2
        
        while retry_count <= max_retries:
            cursor = None
            try:
                # Double-check connection before use
                if not self.connection or not self.connection.is_connected():
                    logger.warning(f"📊 Connection lost before storing data for {device_id}")
                    if not self.ensure_connection():
                        return
                
                cursor = self.connection.cursor(buffered=True)
                cursor.execute(
                    "INSERT INTO sensor_data (device_id, payload) VALUES (%s, %s)",
                    (device_id, json.dumps(payload))
                )
                # No need for explicit commit since autocommit=True
                logger.debug(f"📝 Stored sensor data for {device_id}")
                return  # Success
                
            except mysql.connector.OperationalError as e:
                # Connection lost during operation
                if e.errno in [2013, 2006]:  # Lost connection, MySQL server has gone away
                    log_critical_error("db", e, f"Connection lost while storing data for {device_id} (attempt {retry_count + 1})")
                    self._close_connection()
                    
                    if retry_count < max_retries:
                        retry_count += 1
                        logger.info(f"🔄 Retrying database operation for {device_id} (attempt {retry_count + 1})")
                        if self.ensure_connection():
                            continue  # Retry
                    
                    logger.error(f"💥 Failed to store sensor data for {device_id} after {max_retries + 1} attempts")
                    return
                else:
                    log_critical_error("db", e, f"Database operational error for {device_id}")
                    return
                    
            except mysql.connector.Error as e:
                log_critical_error("db", e, f"Database error storing data for {device_id}")
                return
                
            except Exception as e:
                log_critical_error("db", e, f"Unexpected error storing sensor data for {device_id}")
                return
            finally:
                # Always close cursor
                if cursor:
                    try:
                        cursor.close()
                    except:
                        pass

    def get_recent_data(self, hours: int = 24) -> List[dict]:
        """Get recent sensor data with automatic reconnection"""
        if not self.ensure_connection():
            logger.warning("📊 Cannot retrieve sensor data - database connection unavailable")
            return []
        
        retry_count = 0
        max_retries = 2
        
        while retry_count <= max_retries:
            cursor = None
            try:
                # Double-check connection before use
                if not self.connection or not self.connection.is_connected():
                    logger.warning("📊 Connection lost before retrieving data")
                    if not self.ensure_connection():
                        return []
                
                cursor = self.connection.cursor(buffered=True)
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
                        payload = json.loads(str(payload_str))  # Ensure it's a string
                        results.append({
                            'device_id': device_id,
                            'payload': payload,
                            'timestamp': str(timestamp)
                        })
                    except json.JSONDecodeError:
                        logger.warning(f"⚠️ Invalid JSON in sensor data for {device_id}")
                        continue
                
                return results
                
            except mysql.connector.OperationalError as e:
                # Connection lost during operation
                if e.errno in [2013, 2006]:  # Lost connection, MySQL server has gone away
                    log_critical_error("db", e, f"Connection lost while retrieving data (attempt {retry_count + 1})")
                    self._close_connection()
                    
                    if retry_count < max_retries:
                        retry_count += 1
                        logger.info(f"🔄 Retrying database query (attempt {retry_count + 1})")
                        if self.ensure_connection():
                            continue  # Retry
                    
                    logger.error(f"💥 Failed to retrieve sensor data after {max_retries + 1} attempts")
                    return []
                else:
                    log_critical_error("db", e, "Database operational error during data retrieval")
                    return []
                    
            except mysql.connector.Error as e:
                log_critical_error("db", e, "Database error during data retrieval")
                return []
                
            except Exception as e:
                log_critical_error("db", e, "Unexpected error during data retrieval")
                return []
            finally:
                # Always close cursor
                if cursor:
                    try:
                        cursor.close()
                    except:
                        pass
        
        return []  # Return empty list if all retries failed

    def save_override(self, device_id: str, status: str, override_type: str, expires_at: Optional[datetime] = None):
        """Save device override to database"""
        if not self.ensure_connection():
            logger.warning("📊 Cannot save override - database connection unavailable")
            return
        
        cursor = None
        try:
            cursor = self.connection.cursor(buffered=True)
            cursor.execute("""
                INSERT INTO device_overrides (device_id, status, override_type, expires_at)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                status = VALUES(status),
                override_type = VALUES(override_type),
                expires_at = VALUES(expires_at),
                created_at = CURRENT_TIMESTAMP
            """, (device_id, status, override_type, expires_at))
            # No need for explicit commit since autocommit=True
            print(f"💾 Override saved to database: {device_id} = {status}")
        except mysql.connector.Error as e:
            print(f"❌ Override save error: {e}")
        except Exception as e:
            log_critical_error("db", e, f"Unexpected error saving override for {device_id}")
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass

    def load_overrides(self):
        """Load active overrides from database"""
        if not self.ensure_connection():
            logger.warning("📊 Cannot load overrides - database connection unavailable")
            return {}
        
        cursor = None
        try:
            cursor = self.connection.cursor(buffered=True)
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
            
            return overrides
        except mysql.connector.Error as e:
            print(f"❌ Override load error: {e}")
            return {}
        except Exception as e:
            log_critical_error("db", e, "Unexpected error loading overrides")
            return {}
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass

    def get_energy_stats(self):
        """Get current energy statistics from database"""
        # Attempt reconnection if database is down
        if not self.ensure_connection():
            print("❌ Cannot get energy stats - database unavailable")
            return {
                "total_decisions": 0,
                "energy_saved": 0.0,
                "ambient_overrides": 0,
                "optimization_events": 0
            }
        
        cursor = None
        try:
            cursor = self.connection.cursor(buffered=True)
            cursor.execute("SELECT total_decisions, energy_saved, ambient_overrides, optimization_events FROM energy_stats WHERE id = 1")
            row = cursor.fetchone()
            
            if row:
                return {
                    "total_decisions": int(row[0]),
                    "energy_saved": float(row[1]),
                    "ambient_overrides": int(row[2]),
                    "optimization_events": int(row[3])
                }
            else:
                return {
                    "total_decisions": 0,
                    "energy_saved": 0.0,
                    "ambient_overrides": 0,
                    "optimization_events": 0
                }
        except mysql.connector.Error as e:
            print(f"❌ Energy stats get error: {e}")
            self._close_connection()  # Reset connection on error
            return {
                "total_decisions": 0,
                "energy_saved": 0.0,
                "ambient_overrides": 0,
                "optimization_events": 0
            }
        except Exception as e:
            log_critical_error("db", e, "Unexpected error getting energy stats")
            return {
                "total_decisions": 0,
                "energy_saved": 0.0,
                "ambient_overrides": 0,
                "optimization_events": 0
            }
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass

    def update_energy_stats(self, total_decisions=None, energy_saved=None, ambient_overrides=None, optimization_events=None, baseline_energy=None, ml_energy=None):
        """Update energy statistics in database"""
        if not self.ensure_connection():
            logger.warning("📊 Cannot update energy stats - database connection unavailable")
            return
        
        cursor = None
        try:
            # Build dynamic update query based on provided parameters
            updates = []
            values = []
            
            if total_decisions is not None:
                updates.append("total_decisions = %s")
                values.append(total_decisions)
            if energy_saved is not None:
                updates.append("energy_saved = %s")
                values.append(energy_saved)
            if ambient_overrides is not None:
                updates.append("ambient_overrides = %s")
                values.append(ambient_overrides)
            if optimization_events is not None:
                updates.append("optimization_events = %s")
                values.append(optimization_events)
            if baseline_energy is not None:
                updates.append("baseline_energy = %s")
                values.append(baseline_energy)
            if ml_energy is not None:
                updates.append("ml_energy = %s")
                values.append(ml_energy)
            
            if updates:
                query = f"UPDATE energy_stats SET {', '.join(updates)} WHERE id = 1"
                cursor = self.connection.cursor(buffered=True)
                cursor.execute(query, values)
                # No need for explicit commit since autocommit=True
                
        except mysql.connector.Error as e:
            print(f"❌ Energy stats update error: {e}")
        except Exception as e:
            log_critical_error("db", e, "Unexpected error updating energy stats")
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass

    def increment_energy_stats(self, total_decisions=0, energy_saved=0.0, ambient_overrides=0, optimization_events=0, baseline_energy=0.0, ml_energy=0.0):
        """Increment energy statistics in database"""
        # Attempt reconnection if database is down
        if not self.ensure_connection():
            print("❌ Cannot increment energy stats - database unavailable")
            return
        
        cursor = None
        try:
            cursor = self.connection.cursor(buffered=True)
            cursor.execute("""
                UPDATE energy_stats SET 
                    total_decisions = total_decisions + %s,
                    energy_saved = energy_saved + %s,
                    ambient_overrides = ambient_overrides + %s,
                    optimization_events = optimization_events + %s,
                    baseline_energy = baseline_energy + %s,
                    ml_energy = ml_energy + %s
                WHERE id = 1
            """, (total_decisions, energy_saved, ambient_overrides, optimization_events, baseline_energy, ml_energy))
            # No need for explicit commit since autocommit=True
            
            # Debug logging for successful increments
            if total_decisions > 0 or energy_saved > 0 or ambient_overrides > 0 or optimization_events > 0:
                print(f"📊 Stats updated: decisions+{total_decisions}, energy_saved+{energy_saved:.3f}kWh, ambient+{ambient_overrides}, events+{optimization_events}")
                
        except mysql.connector.Error as e:
            print(f"❌ Energy stats increment error: {e}")
            self._close_connection()  # Reset connection on error
        except Exception as e:
            log_critical_error("db", e, "Unexpected error incrementing energy stats")
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass

# Initialize database with health monitoring
db = DatabaseManager()

def database_health_monitor():
    """Background thread to monitor database connection health"""
    import time
    while True:
        try:
            time.sleep(30)  # Check every 30 seconds
            if not db.is_connected():
                logger.warning("🏥 Database health check failed, attempting reconnection...")
                db.ensure_connection()
            else:
                logger.debug("💚 Database health check passed")
        except Exception as e:
            log_critical_error("db", e, "Database health monitor error")
            time.sleep(60)  # Wait longer on error

# Start database health monitoring thread
db_health_thread = threading.Thread(target=database_health_monitor, daemon=True)
db_health_thread.start()
logger.info("🏥 Database health monitoring started")

def load_ml_model():
    """Load trained ML model and parameters"""
    model = None
    feature_stats = None
    params = None
    
    logger.info("🧠 Loading ML model and parameters...")
    
    # Try to load the actual trained model
    try:
        model = joblib.load('/app/ml/energy_saving_lighting_model.joblib')
        logger.info("✅ Trained ML model loaded successfully")
    except FileNotFoundError:
        logger.warning("⚠️ Trained model not found at /app/ml/energy_saving_lighting_model.joblib")
        logger.info("📁 Using rule-based fallback")
    except (ImportError, ModuleNotFoundError) as e:
        if 'numpy' in str(e).lower():
            log_critical_error("ml", e, "NumPy compatibility issue - model training environment mismatch")
        else:
            log_critical_error("ml", e, "Missing dependencies for ML model")
        model = None
    except Exception as e:
        # Catch version compatibility issues that can cause segfaults
        error_msg = str(e).lower()
        if 'version' in error_msg or 'unpickle' in error_msg or 'incompatible' in error_msg:
            log_critical_error("ml", e, "Model version compatibility issue - potential crash risk")
            logger.error("🔧 SOLUTION: Update scikit-learn version or retrain model")
        else:
            log_critical_error("ml", e, "Unexpected ML model loading error")
        logger.warning("⚠️ Using rule-based fallback to prevent crashes")
        model = None
    
    # Load feature statistics for normalization
    try:
        with open('/app/ml/feature_stats.json', 'r') as f:
            feature_stats = json.load(f)
        logger.info("✅ Feature statistics loaded")
    except FileNotFoundError:
        logger.warning("⚠️ Feature stats not found at /app/ml/feature_stats.json")
    except Exception as e:
        log_critical_error("ml", e, "Failed to load feature statistics")
    
    # Load model parameters
    try:
        with open('/app/ml/train_params.json', 'r') as f:
            params = json.load(f)
        logger.info("✅ Model parameters loaded")
    except FileNotFoundError:
        logger.warning("⚠️ Model parameters not found, using fallback parameters")
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
    except Exception as e:
        log_critical_error("ml", e, "Failed to load model parameters")
        params = {
            "model_type": "energy_saving_lighting_control_fallback",
            "objective": "minimize_lighting_energy_consumption",
            "energy_efficiency_improvement": "N/A",
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
    try:
        # Validate input
        if not device_id or not isinstance(payload, dict):
            logger.warning(f"⚠️ Invalid sensor data: device_id={device_id}, payload={type(payload)}")
            return
        
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
            logger.debug(f"🎛️ Override active: {device_id} = {override_status} ({reason}) - skipping automatic control")
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
            db.increment_energy_stats(ambient_overrides=1)
            reason += "_ambient_sufficient"
        
        # Only update stats if LED command actually changed
        last_command = last_device_states.get(device_id)
        if last_command != led_command:
            # Update global stats only on actual state change
            db.increment_energy_stats(total_decisions=1, energy_saved=energy_saved)
            
            # Increment ML optimizations counter when ML model is used
            if trained_model and 'ml_prediction' in reason:
                db.increment_energy_stats(optimization_events=1)
            
            last_device_states[device_id] = led_command
            
            logger.info(f"⚡ {device_id}: {original_command} → {led_command}, saved: {energy_saved:.3f}kWh vs baseline")
            logger.debug(f"   🤖 Decision method: {'ML Model' if trained_model and 'ml_prediction' in reason else 'Rule-based'}")
            logger.debug(f"   💡 Baseline would use: {0.15 if payload.get('occupancy', 0) > 0 else 0.0:.3f}kWh (150W when occupied)")
            logger.debug(f"   📊 Reason: {reason}")
        
        # Send LED command (only when no override is active)
        try:
            actuator_topic = f"actuators/{device_id}/led"
            publish.single(actuator_topic, led_command, hostname=MQTT_BROKER, port=MQTT_PORT)
            logger.debug(f"📡 Sent command to {actuator_topic}: {led_command}")
        except Exception as e:
            log_critical_error("mqtt", e, f"Failed to publish LED command for {device_id}")
            
    except Exception as e:
        log_critical_error("sensor", e, f"Failed to process sensor data for {device_id}")

# MQTT Event Handlers
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"✅ MQTT connected to {MQTT_BROKER}:{MQTT_PORT}")
        try:
            client.subscribe("sensors/+/data")
            client.subscribe("sensors/+/button")
            logger.info("📡 MQTT subscriptions established")
        except Exception as e:
            log_critical_error("mqtt", e, "Failed to establish MQTT subscriptions")
    else:
        log_critical_error("mqtt", Exception(f"Connection failed with code {rc}"), f"MQTT connection to {MQTT_BROKER}:{MQTT_PORT}")

def on_message(client, userdata, msg):
    try:
        # Validate message structure
        if not msg.topic or not msg.payload:
            logger.warning(f"⚠️ Received invalid MQTT message: topic={msg.topic}, payload={msg.payload}")
            return
            
        device_id = msg.topic.split('/')[1]  # Extract device_id from topic
        
        # Validate device_id
        if not device_id or device_id == '+':
            logger.warning(f"⚠️ Invalid device_id extracted from topic: {msg.topic}")
            return
            
        payload = json.loads(msg.payload.decode())
        
        # Log message processing (debug level to avoid spam)
        logger.debug(f"📨 Processing message from {device_id}: {msg.topic}")
        
        if "/button" in msg.topic:
            # Handle button press - toggle override
            logger.info(f"🔘 Button press detected for {device_id}")
            current_override = check_device_override(device_id)
            if current_override:
                set_device_override(device_id, "disabled", "disabled")
                logger.info(f"🔘 Button press: {device_id} override disabled")
            else:
                # Set 24h override to opposite of current ML decision
                action, _, _ = energy_saving_decision(latest_sensor_data.get(device_id, {}))
                new_status = "on" if action == "turn_off" else "off"
                set_device_override(device_id, new_status, "24h")
                logger.info(f"🔘 Button press: {device_id} override set to {new_status} (24h)")
        else:
            # Regular sensor data
            logger.debug(f"📊 Processing sensor data for {device_id}")
            process_sensor_data(device_id, payload)
            
    except json.JSONDecodeError as e:
        log_critical_error("mqtt", e, f"JSON decode error for topic {msg.topic}")
    except IndexError as e:
        log_critical_error("mqtt", e, f"Topic parsing error for {msg.topic}")
    except KeyError as e:
        log_critical_error("mqtt", e, f"Missing key in payload for {msg.topic}")
    except Exception as e:
        log_critical_error("mqtt", e, f"Unexpected MQTT message processing error for topic {msg.topic}")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        log_critical_error("mqtt", Exception(f"Unexpected disconnect with code {rc}"), "MQTT client unexpectedly disconnected")
    else:
        logger.info("📡 MQTT client disconnected gracefully")

def on_log(client, userdata, level, buf):
    """MQTT client logging callback"""
    if level == mqtt.MQTT_LOG_ERR:
        logger.error(f"📡 MQTT ERROR: {buf}")
    elif level == mqtt.MQTT_LOG_WARNING:
        logger.warning(f"📡 MQTT WARNING: {buf}")
    else:
        logger.debug(f"📡 MQTT: {buf}")

# Load existing overrides
device_overrides = db.load_overrides()
print(f"📋 Loaded {len(device_overrides)} existing overrides")

# REST API Endpoints
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring"""
    try:
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'database': 'connected' if db.connection else 'disconnected',
                'ml_model': 'loaded' if trained_model else 'rule_based_fallback',
                'mqtt': 'running',  # If we're responding, MQTT thread is likely running
                'api': 'running'
            },
            'error_counts': critical_ops,
            'uptime_info': {
                'active_overrides': len(device_overrides),
                'devices_tracked': len(latest_sensor_data),
                'last_device_states': len(last_device_states)
            }
        }
        
        # Determine overall health
        if critical_ops.get("db_errors", 0) > 10 or critical_ops.get("mqtt_errors", 0) > 10:
            health_status['status'] = 'degraded'
        
        if not db.connection:
            health_status['status'] = 'unhealthy'
            
        return jsonify(health_status)
    except Exception as e:
        log_critical_error("api", e, "Health check endpoint failed")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get system status"""
    return jsonify({
        'status': 'running',
        'energy_stats': db.get_energy_stats(),
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
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400
        
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
    if hours is None:
        hours = 24
    data = db.get_recent_data(hours)
    return jsonify(data)

@app.route('/api/energy-stats', methods=['GET'])
def get_energy_stats():
    """Get energy optimization statistics"""
    return jsonify(db.get_energy_stats())

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
    # Get current energy stats from database
    current_energy_stats = db.get_energy_stats()
    
    if total_baseline_energy > 0:
        efficiency_improvement = (current_energy_stats['energy_saved'] / total_baseline_energy) * 100
    
    comparison_stats = {
        'baseline_assumption': 'Lights always ON when room is occupied (150W per room)',
        'current_baseline_consumption_kw': total_baseline_energy,
        'rooms_currently_occupied': total_rooms_occupied,
        'ml_energy_saved_vs_baseline_kwh': current_energy_stats['energy_saved'],
        'efficiency_improvement_percent': round(efficiency_improvement, 1),
        'total_ml_decisions': current_energy_stats['optimization_events'],
        'total_system_decisions': current_energy_stats['total_decisions'],
        'ml_model_active': trained_model is not None,
        'energy_stats': current_energy_stats,
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
    if not data:
        return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
        
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
    """Start MQTT client in separate thread with automatic reconnection"""
    logger.info("📡 Starting MQTT client...")
    
    def create_mqtt_client():
        """Create and configure MQTT client"""
        client = mqtt.Client(client_id="iot_controller")
        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        client.on_log = on_log
        
        # Configure MQTT client settings for better reliability
        client.reconnect_delay_set(min_delay=1, max_delay=120)
        client.max_inflight_messages_set(20)
        client.max_queued_messages_set(100)
        
        return client
    
    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries:
        try:
            client = create_mqtt_client()
            logger.info(f"📡 Connecting to MQTT broker {MQTT_BROKER}:{MQTT_PORT} (attempt {retry_count + 1})")
            
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            logger.info("📡 MQTT client connected successfully")
            
            # Start the loop - this will handle reconnections automatically
            client.loop_forever()
            
        except ConnectionRefusedError as e:
            retry_count += 1
            log_critical_error("mqtt", e, f"MQTT connection refused (attempt {retry_count})")
            if retry_count < max_retries:
                wait_time = min(2 ** retry_count, 60)  # Exponential backoff, max 60 seconds
                logger.warning(f"⏳ Retrying MQTT connection in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error("💥 MQTT connection failed after max retries")
                break
                
        except Exception as e:
            retry_count += 1
            log_critical_error("mqtt", e, f"MQTT client error (attempt {retry_count})")
            if retry_count < max_retries:
                wait_time = min(2 ** retry_count, 60)
                logger.warning(f"⏳ Retrying MQTT connection in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error("💥 MQTT client failed after max retries")
                break

# Add Flask error handlers
@app.errorhandler(404)
def not_found_error(error):
    critical_ops["api_errors"] += 1
    logger.warning(f"🌐 API 404 error: {request.url}")
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    log_critical_error("api", error, f"Internal server error for {request.url}")
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    log_critical_error("api", e, f"Unhandled exception for {request.url}")
    return jsonify({'error': 'An unexpected error occurred'}), 500

if __name__ == "__main__":
    try:
        logger.info("🚀 IoT Energy Management Controller Starting...")
        logger.info(f"🌐 REST API will be available on port 5001")
        logger.info(f"📡 MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
        logger.info(f"🗄️ Database: {MYSQL_HOST}/{MYSQL_DB}")
        logger.info(f"📊 Critical operations monitoring enabled")
        
        # Test database connection on startup
        if not db.connection:
            logger.error("💥 STARTUP FAILED: Database connection unavailable")
            sys.exit(1)
        
        # Start MQTT client in background thread
        logger.info("📡 Starting MQTT client thread...")
        mqtt_thread = threading.Thread(target=start_mqtt_client, daemon=True)
        mqtt_thread.start()
        
        # Give MQTT client time to connect
        time.sleep(2)
        
        # Start Flask REST API with error handling
        logger.info("🌐 Starting Flask REST API server...")
        app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False, threaded=True)
        
    except KeyboardInterrupt:
        logger.info("⏹️ Received keyboard interrupt, shutting down...")
    except Exception as e:
        log_critical_error("startup", e, "Critical startup failure")
        sys.exit(1)
    finally:
        logger.info("🔄 Controller shutdown complete")
        logger.info(f"📊 Final error counts: {critical_ops}")