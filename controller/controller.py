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
import sys
import json
import logging
import re
import signal
import threading
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import joblib
import mysql.connector
import pandas as pd
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
import paho.mqtt.subscribe as subscribe

import asyncio
from aiocoap import Message, Context
from aiocoap.numbers import PUT, GET

# Optional import for border router discovery
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("⚠️ requests module not available - border router discovery disabled")

from flask import Flask, jsonify, request

import asyncio
from aiocoap import Message, Context
from aiocoap.numbers import PUT

# Configuration
MQTT_BROKER = os.environ.get("MQTT_BROKER", "iot_mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))

MYSQL_HOST = os.environ.get("MYSQL_HOST", "iot_mysql")
MYSQL_USER = os.environ.get("MYSQL_USER", "iotuser")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "iotpass")
MYSQL_DB = os.environ.get("MYSQL_DB", "iotdb")

# Temperature prediction constants (matches node configuration)
TEMP_HISTORY_SIZE = 48  # 48 readings = 24 hours at 30-min intervals

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

async def send_coap_request(uri, payload):
    """Send CoAP PUT request to device"""
    logger.info(f"📤 CoAP PUT to {uri}")
    logger.info(f"   Payload length: {len(payload)} bytes")
    logger.info(f"   Payload preview: {payload[:200]}...")  # Log first 200 chars

    request = Message(code=PUT, payload=payload.encode('utf-8'))
    request.set_request_uri(uri)
    logger.info(f"   Creating CoAP context for UDP6 transport...")
    protocol = await Context.create_client_context(transports=['udp6'])
    try:
        logger.info(f"   Sending CoAP request and waiting for response...")
        response = await asyncio.wait_for(protocol.request(request).response, timeout=10.0)
        logger.info(f"📥 CoAP Response: {response.code}")
        response_payload = response.payload.decode('utf-8') if response.payload else ""
        logger.info(f"   Response payload: {response_payload[:200]}")  # Log first 200 chars
        return response_payload
    except asyncio.TimeoutError:
        logger.error(f"❌ CoAP Timeout: No response from {uri} after 10 seconds")
        return None
    except Exception as e:
        logger.error(f"❌ CoAP Error: {e}")
        logger.error(f"   Exception type: {type(e).__name__}")
        logger.error(f"   Stack trace: {traceback.format_exc()}")
        return None
    finally:
        await protocol.shutdown()

async def sync_device_clock(device_id: str) -> bool:
    """
    Synchronize device clock via CoAP PUT /time_sync
    Returns True if sync successful, False otherwise
    """
    try:
        # Get device URI, replacing /settings with /time_sync
        settings_uri = get_device_uri(device_id)
        if not settings_uri:
            # Try to discover neighbors if URI not found
            discover_border_router_neighbors()
            settings_uri = get_device_uri(device_id)
            if not settings_uri:
                logger.warning(f"⏰ Cannot sync {device_id}: no URI available after discovery")
                return False

        # Replace /settings with /time_sync
        time_sync_uri = settings_uri.replace('/settings', '/time_sync')

        # Get current server time
        now = datetime.now()
        day_of_week = now.weekday()  # 0=Monday 6=Sunday
        hour = now.hour
        minute = now.minute

        # Build JSON payload
        payload = json.dumps({
            "day": day_of_week,
            "hour": hour,
            "minute": minute
        })

        logger.info(f"⏰ Syncing {device_id} to server time: Day {day_of_week}, {hour:02d}:{minute:02d}")

        # Send CoAP PUT request
        request = Message(code=PUT, payload=payload.encode('utf-8'))
        request.set_request_uri(time_sync_uri)
        protocol = await Context.create_client_context(transports=['udp6'])

        try:
            response = await protocol.request(request).response
            if response.code.is_successful():
                logger.info(f"✅ Clock sync successful for {device_id}: {response.code}")
                return True
            else:
                logger.warning(f"⚠️ Clock sync failed for {device_id}: {response.code}")
                return False
        except Exception as e:
            logger.error(f"❌ Clock sync error for {device_id}: {e}")
            return False
        finally:
            await protocol.shutdown()

    except Exception as e:
        log_critical_error("coap", e, f"Failed to sync clock for {device_id}")
        return False

async def query_device_id(ip_address: str) -> Optional[str]:
    """
    Query a device for its ID via CoAP GET request
    Returns device_id or None if query fails
    """
    uri = f"coap://[{ip_address}]/settings"
    request = Message(code=GET)
    request.set_request_uri(uri)
    protocol = await Context.create_client_context(transports=['udp6'])
    try:
        response = await protocol.request(request).response
        logger.debug(f"📡 CoAP response from {ip_address}: code={response.code}, payload_length={len(response.payload)}")

        if response.code.is_successful():
            # Handle potentially truncated/corrupted JSON responses
            raw_payload = response.payload.decode('utf-8', errors='ignore')
            logger.debug(f"📡 Raw payload from {ip_address}: {repr(raw_payload)}")

            # Try to extract device_id using regex from the raw response
            import re
            device_id_match = re.search(r'"device_id"\s*:\s*"([^"]+)"', raw_payload)
            if device_id_match:
                device_id = device_id_match.group(1)
                logger.info(f"📡 Queried {ip_address} -> device_id: {device_id}")
                return device_id

            # Fallback: try other possible field names
            for field in ['id', 'node_id', 'name']:
                match = re.search(rf'"{field}"\s*:\s*"([^"]+)"', raw_payload)
                if match:
                    device_id = match.group(1)
                    logger.info(f"📡 Queried {ip_address} -> {field}: {device_id}")
                    return device_id

            logger.warning(f"⚠️ No device identifier found in response from {ip_address}")
        else:
            logger.warning(f"⚠️ CoAP query failed for {ip_address}: {response.code}")
    except Exception as e:
        logger.warning(f"⚠️ CoAP query error for {ip_address}: {e}")
    finally:
        await protocol.shutdown()

    return None

def get_device_uri(device_id: str) -> Optional[str]:
    """
    Get CoAP URI for a device dynamically
    Priority order: MQTT payload IP -> Border router discovery cache -> Hardcoded patterns
    """
    # First priority: Check if URI is stored in latest sensor data (from MQTT payload)
    if device_id in latest_sensor_data:
        device_data = latest_sensor_data[device_id]
        # Check if URI is stored in device data
        if 'coap_uri' in device_data:
            uri = device_data['coap_uri']
            logger.debug(f"📡 Using MQTT-provided URI for {device_id}: {uri}")
            return uri

    # Second priority: Use cached border router neighbor mappings (DO NOT trigger discovery here!)
    # Discovery is only triggered periodically in background or on explicit request
    if device_id in border_router_neighbors:
        ip_addr = border_router_neighbors[device_id]
        uri = f"coap://[{ip_addr}]/settings"
        logger.debug(f"🌐 Using cached border router URI for {device_id}: {uri}")
        return uri

    # Third priority: Fallback to hardcoded patterns
    # This assumes a standard IPv6 pattern for Contiki nodes
    # In a production system, URIs would be stored in database during device registration
    # border router shows data on http://[fd00::f6ce:365a:bb21:6e94], normally
    uri_patterns = {
        "node1": "coap://[fd00::f6ce:3686:4ff2:1a3]/settings",
        "node2": "coap://[fd00::f6ce:3613:93ee:6aad]/settings",
        "node3": "coap://[fd00::f6ce:3673:822d:d8c7]/settings",
    }

    uri = uri_patterns.get(device_id)
    if uri:
        logger.debug(f"📋 Using hardcoded fallback URI for {device_id}: {uri}")

    return uri

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
        self.pool = None
        self.connection_attempts = 0
        self.max_retries = 5
        self.connect()

    def connect(self):
        """Create a connection pool with retry logic"""
        while self.connection_attempts < self.max_retries:
            try:
                logger.info(f"🔗 Creating database connection pool for {MYSQL_HOST}:{MYSQL_DB} (attempt {self.connection_attempts + 1})")
                self.pool = mysql.connector.pooling.MySQLConnectionPool(
                    pool_name="iot_pool",
                    pool_size=10,
                    host=MYSQL_HOST,
                    user=MYSQL_USER,
                    password=MYSQL_PASSWORD,
                    database=MYSQL_DB,
                    connect_timeout=10,
                    autocommit=True,
                    buffered=True,
                    raise_on_warnings=False,
                    sql_mode='',
                    use_unicode=True,
                    charset='utf8mb4'
                )
                # Test the pool by getting a connection
                conn = self.pool.get_connection()
                conn.close()
                logger.info("✅ Database connection pool created successfully.")
                self._create_tables()
                return
            except mysql.connector.Error as e:
                self.connection_attempts += 1
                log_critical_error("db", e, f"Failed to create connection pool (attempt {self.connection_attempts})")
                if self.connection_attempts < self.max_retries:
                    time.sleep(5)
                else:
                    logger.error("💥 Could not establish database connection after multiple retries.")
                    self.pool = None
            except Exception as e:
                log_critical_error("db", e, "Unexpected error creating connection pool")
                self.pool = None
                break

    def get_connection(self):
        """Get a connection from the pool"""
        if not self.pool:
            logger.error("❌ Connection pool is not available.")
            # Try to reconnect
            self.connect()
            if not self.pool:
                raise Exception("Database connection pool is unavailable.")

        try:
            return self.pool.get_connection()
        except mysql.connector.Error as e:
            log_critical_error("db", e, "Failed to get connection from pool")
            # If pool is broken, try to re-establish it
            self.connect()
            if self.pool:
                return self.pool.get_connection()
            raise e

    def _create_tables(self):
        """Create database tables with error handling"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
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

                # Border router mappings table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS border_router_mappings (
                        device_id VARCHAR(50) PRIMARY KEY,
                        ip_address VARCHAR(50) NOT NULL,
                        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_last_seen (last_seen)
                    )
                """)

                # Device schedules table - stores per-device temperature schedules
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS device_schedules (
                        device_id VARCHAR(50) PRIMARY KEY,
                        schedule JSON NOT NULL COMMENT 'Array of 168 hourly temperatures (7 days * 24 hours)',
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        last_broadcast TIMESTAMP NULL COMMENT 'Last time schedule was sent to device',
                        INDEX idx_last_broadcast (last_broadcast)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)

                # Temperature schedules table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS temperature_schedules (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        description TEXT,
                        schedule_data JSON NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        INDEX idx_created (created_at)
                    )
                """)

                # Ensure there's always one row for energy stats
                cursor.execute("""
                    INSERT IGNORE INTO energy_stats (id, total_decisions, energy_saved, ambient_overrides, optimization_events, baseline_energy, ml_energy)
                    VALUES (1, 0, 0.000, 0, 0, 0.000, 0.000)
                """)

                logger.info("📊 Database tables created/verified successfully")
        except mysql.connector.Error as e:
            log_critical_error("db", e, "Failed to create database tables")
        except Exception as e:
            log_critical_error("db", e, "Unexpected error creating database tables")
        finally:
            if conn and conn.is_connected():
                conn.close()

    def store_sensor_data(self, device_id: str, payload: dict):
        """Store sensor data in database using a connection from the pool"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO sensor_data (device_id, payload) VALUES (%s, %s)",
                    (device_id, json.dumps(payload))
                )
            logger.debug(f"📝 Stored sensor data for {device_id}")
        except mysql.connector.Error as e:
            log_critical_error("db", e, f"Database error storing data for {device_id}")
        except Exception as e:
            log_critical_error("db", e, f"Unexpected error storing sensor data for {device_id}")
        finally:
            if conn and conn.is_connected():
                conn.close()

    def get_recent_data(self, hours: int = 24) -> List[dict]:
        """Get recent sensor data using a connection from the pool"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT device_id, payload, timestamp
                    FROM sensor_data
                    WHERE timestamp >= NOW() - INTERVAL %s HOUR
                    ORDER BY timestamp DESC
                """, (hours,))

                results = cursor.fetchall()
                # Manually convert payload from string to dict if needed
                for row in results:
                    if isinstance(row['payload'], str):
                        row['payload'] = json.loads(row['payload'])
                return results
        except mysql.connector.Error as e:
            log_critical_error("db", e, "Database error during data retrieval")
            return []
        except Exception as e:
            log_critical_error("db", e, "Unexpected error during data retrieval")
            return []
        finally:
            if conn and conn.is_connected():
                conn.close()

    def save_override(self, device_id: str, status: str, override_type: str, expires_at: Optional[datetime] = None):
        """Save device override to database"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO device_overrides (device_id, status, override_type, expires_at)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    status = VALUES(status),
                    override_type = VALUES(override_type),
                    expires_at = VALUES(expires_at),
                    created_at = CURRENT_TIMESTAMP
                """, (device_id, status, override_type, expires_at))
            print(f"💾 Override saved to database: {device_id} = {status}")
        except mysql.connector.Error as e:
            print(f"❌ Override save error: {e}")
        except Exception as e:
            log_critical_error("db", e, f"Unexpected error saving override for {device_id}")
        finally:
            if conn and conn.is_connected():
                conn.close()

    def load_overrides(self):
        """Load active overrides from database"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT device_id, status, override_type, expires_at
                    FROM device_overrides
                    WHERE expires_at IS NULL OR expires_at > NOW()
                """)

                overrides = {}
                for row in cursor.fetchall():
                    overrides[row['device_id']] = {
                        'status': row['status'],
                        'type': row['override_type'],
                        'expires_at': row['expires_at']
                    }
                return overrides
        except mysql.connector.Error as e:
            print(f"❌ Override load error: {e}")
            return {}
        except Exception as e:
            log_critical_error("db", e, "Unexpected error loading overrides")
            return {}
        finally:
            if conn and conn.is_connected():
                conn.close()

    def delete_override(self, device_id: str):
        """Delete device override from database"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM device_overrides WHERE device_id = %s", (device_id,))
            print(f"💾 Override deleted from database: {device_id}")
        except mysql.connector.Error as e:
            print(f"❌ Override delete error: {e}")
        except Exception as e:
            log_critical_error("db", e, f"Unexpected error deleting override for {device_id}")
        finally:
            if conn and conn.is_connected():
                conn.close()

    def get_energy_stats(self):
        """Get current energy statistics from database"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT total_decisions, energy_saved, ambient_overrides, optimization_events FROM energy_stats WHERE id = 1")
                row = cursor.fetchone()

            if row:
                return {
                    "total_decisions": int(row[0]),
                    "energy_saved": float(row[1]),
                    "ambient_overrides": int(row[2]),
                    "optimization_events": int(row[3])
                }
        except mysql.connector.Error as e:
            print(f"❌ Energy stats get error: {e}")
        except Exception as e:
            log_critical_error("db", e, "Unexpected error getting energy stats")
        finally:
            if conn and conn.is_connected():
                conn.close()

        # Fallback if anything goes wrong
        return {
            "total_decisions": 0, "energy_saved": 0.0,
            "ambient_overrides": 0, "optimization_events": 0
        }

    def update_energy_stats(self, total_decisions=None, energy_saved=None, ambient_overrides=None, optimization_events=None, baseline_energy=None, ml_energy=None):
        """Update energy statistics in database"""
        conn = None
        try:
            updates = []
            values = []

            if total_decisions is not None: updates.append("total_decisions = %s"); values.append(total_decisions)
            if energy_saved is not None: updates.append("energy_saved = %s"); values.append(energy_saved)
            if ambient_overrides is not None: updates.append("ambient_overrides = %s"); values.append(ambient_overrides)
            if optimization_events is not None: updates.append("optimization_events = %s"); values.append(optimization_events)
            if baseline_energy is not None: updates.append("baseline_energy = %s"); values.append(baseline_energy)
            if ml_energy is not None: updates.append("ml_energy = %s"); values.append(ml_energy)

            if updates:
                conn = self.get_connection()
                with conn.cursor() as cursor:
                    query = f"UPDATE energy_stats SET {', '.join(updates)} WHERE id = 1"
                    cursor.execute(query, values)
        except mysql.connector.Error as e:
            print(f"❌ Energy stats update error: {e}")
        except Exception as e:
            log_critical_error("db", e, "Unexpected error updating energy stats")
        finally:
            if conn and conn.is_connected():
                conn.close()

    def increment_energy_stats(self, total_decisions=0, energy_saved=0.0, ambient_overrides=0, optimization_events=0, baseline_energy=0.0, ml_energy=0.0):
        """Increment energy statistics in database"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
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

            if total_decisions > 0 or energy_saved > 0 or ambient_overrides > 0 or optimization_events > 0:
                print(f"📊 Stats updated: decisions+{total_decisions}, energy_saved+{energy_saved:.3f}kWh, ambient+{ambient_overrides}, events+{optimization_events}")
        except mysql.connector.Error as e:
            print(f"❌ Energy stats increment error: {e}")
        except Exception as e:
            log_critical_error("db", e, "Unexpected error incrementing energy stats")
        finally:
            if conn and conn.is_connected():
                conn.close()

    def get_device_locations_from_db(self) -> Dict[str, str]:
        """Get device-to-location mapping from database for all devices that have ever transmitted data"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(dictionary=True) as cursor:
                # Get the most recent location for each device that has ever transmitted data
                cursor.execute("""
                    SELECT device_id, JSON_UNQUOTE(JSON_EXTRACT(payload, '$.location')) as location
                    FROM sensor_data
                    WHERE JSON_EXTRACT(payload, '$.location') IS NOT NULL
                    AND JSON_EXTRACT(payload, '$.location') != 'null'
                    ORDER BY timestamp DESC
                """)

                locations = {}
                seen_devices = set()

                for row in cursor.fetchall():
                    device_id = row['device_id']
                    location = row['location']

                    # Only take the first (most recent) entry for each device
                    if device_id not in seen_devices and location:
                        locations[device_id] = location
                        seen_devices.add(device_id)

                return locations
        except mysql.connector.Error as e:
            log_critical_error("db", e, "Database error getting device locations")
            return {}
        except Exception as e:
            log_critical_error("db", e, "Unexpected error getting device locations")
            return {}
        finally:
            if conn and conn.is_connected():
                conn.close()

    def save_border_router_mapping(self, device_id: str, ip_address: str):
        """Save border router device mapping to database"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO border_router_mappings (device_id, ip_address, last_seen)
                    VALUES (%s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                    ip_address = VALUES(ip_address),
                    last_seen = NOW()
                """, (device_id, ip_address))
            logger.debug(f"💾 Saved border router mapping: {device_id} -> {ip_address}")
        except mysql.connector.Error as e:
            log_critical_error("db", e, f"Database error saving border router mapping for {device_id}")
        except Exception as e:
            log_critical_error("db", e, f"Unexpected error saving border router mapping for {device_id}")
        finally:
            if conn and conn.is_connected():
                conn.close()

    def load_border_router_mappings(self) -> Dict[str, str]:
        """Load border router device mappings from database"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(dictionary=True) as cursor:
                # Get mappings that are less than 24 hours old (devices should rediscover if they've been gone too long)
                cursor.execute("""
                    SELECT device_id, ip_address
                    FROM border_router_mappings
                    WHERE last_seen >= NOW() - INTERVAL 24 HOUR
                """)

                mappings = {}
                for row in cursor.fetchall():
                    mappings[row['device_id']] = row['ip_address']

                return mappings
        except mysql.connector.Error as e:
            log_critical_error("db", e, "Database error loading border router mappings")
            return {}
        except Exception as e:
            log_critical_error("db", e, "Unexpected error loading border router mappings")
            return {}
        finally:
            if conn and conn.is_connected():
                conn.close()

    def cleanup_stale_mappings(self, max_age_hours: int = 24):
        """Remove stale border router mappings older than max_age_hours"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM border_router_mappings
                    WHERE last_seen < NOW() - INTERVAL %s HOUR
                """, (max_age_hours,))
                deleted_count = cursor.rowcount
                conn.commit()
                if deleted_count > 0:
                    logger.info(f"🧹 Cleaned up {deleted_count} stale border router mappings")
        except mysql.connector.Error as e:
            log_critical_error("db", e, "Database error cleaning up stale mappings")
        except Exception as e:
            log_critical_error("db", e, "Unexpected error cleaning up stale mappings")
        finally:
            if conn and conn.is_connected():
                conn.close()

    def save_device_schedule(self, device_id: str, schedule: list):
        """Save weekly temperature schedule for a device (168 hourly values)"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                schedule_json = json.dumps(schedule)
                cursor.execute("""
                    INSERT INTO device_schedules (device_id, schedule, last_updated)
                    VALUES (%s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                    schedule = VALUES(schedule),
                    last_updated = NOW()
                """, (device_id, schedule_json))
                conn.commit()
                logger.info(f"💾 Saved schedule for {device_id} ({len(schedule)} values)")
        except mysql.connector.Error as e:
            log_critical_error("db", e, f"Database error saving schedule for {device_id}")
        except Exception as e:
            log_critical_error("db", e, f"Unexpected error saving schedule for {device_id}")
        finally:
            if conn and conn.is_connected():
                conn.close()

    def load_device_schedule(self, device_id: str) -> Optional[list]:
        """Load weekly temperature schedule for a device"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT schedule, last_updated, last_broadcast
                    FROM device_schedules
                    WHERE device_id = %s
                """, (device_id,))
                result = cursor.fetchone()
                if result:
                    schedule = json.loads(result['schedule'])
                    logger.debug(f"📋 Loaded schedule for {device_id} ({len(schedule)} values)")
                    return schedule
                return None
        except mysql.connector.Error as e:
            log_critical_error("db", e, f"Database error loading schedule for {device_id}")
            return None
        except Exception as e:
            log_critical_error("db", e, f"Unexpected error loading schedule for {device_id}")
            return None
        finally:
            if conn and conn.is_connected():
                conn.close()

    def update_schedule_broadcast_time(self, device_id: str):
        """Update last_broadcast timestamp for device schedule"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE device_schedules
                    SET last_broadcast = NOW()
                    WHERE device_id = %s
                """, (device_id,))
                conn.commit()
        except mysql.connector.Error as e:
            log_critical_error("db", e, f"Database error updating broadcast time for {device_id}")
        except Exception as e:
            log_critical_error("db", e, f"Unexpected error updating broadcast time for {device_id}")
        finally:
            if conn and conn.is_connected():
                conn.close()

    def get_devices_needing_schedule_broadcast(self, interval_seconds: int = 300) -> List[str]:
        """Get list of device IDs that need schedule broadcast (first time or periodic refresh)"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(dictionary=True) as cursor:
                # Get devices that have schedules but haven't been broadcast recently
                cursor.execute("""
                    SELECT device_id
                    FROM device_schedules
                    WHERE last_broadcast IS NULL
                       OR last_broadcast < NOW() - INTERVAL %s SECOND
                """, (interval_seconds,))
                devices = [row['device_id'] for row in cursor.fetchall()]
                return devices
        except mysql.connector.Error as e:
            log_critical_error("db", e, "Database error getting devices needing schedule broadcast")
            return []
        except Exception as e:
            log_critical_error("db", e, "Unexpected error getting devices needing schedule broadcast")
            return []
        finally:
            if conn and conn.is_connected():
                conn.close()

# Initialize database with connection pooling
db = DatabaseManager()

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
print(f"🧠 ML System: {model_params.get('model_type', 'disabled')}")
print(f"⚡ Energy efficiency: {model_params.get('energy_efficiency_improvement', 'N/A')}")
print(f"🎯 Operating mode: MANUAL ONLY - No automatic LED control decisions")

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
        db.delete_override(device_id)
        return None

    return override['status']

def set_device_override(device_id: str, status: str, override_type: str = "24h"):
    """
    Set device override with different durations
    override_type: "24h", "permanent", "disabled"
    """
    expires_at = None

    if override_type == "1h":
        expires_at = datetime.now() + timedelta(hours=1)
    elif override_type == "4h":
        expires_at = datetime.now() + timedelta(hours=4)
    elif override_type == "12h":
        expires_at = datetime.now() + timedelta(hours=12)
    elif override_type == "24h":
        expires_at = datetime.now() + timedelta(hours=24)
    elif override_type == "permanent":
        expires_at = None
    elif override_type == "disabled":
        # Remove override
        if device_id in device_overrides:
            del device_overrides[device_id]

        db.delete_override(device_id)

        # Send CoAP to disable override
        uri = get_device_uri(device_id)
        if uri:
            coap_payload = '{"mo": 0, "ab": 1}'  # Disable manual override, enable auto
            asyncio.run(send_coap_request(uri, coap_payload))

        print(f"🎛️ Override removed: {device_id}")
        return

    device_overrides[device_id] = {
        'status': status,
        'type': override_type,
        'expires_at': expires_at
    }

    # Save to database
    db.save_override(device_id, status, override_type, expires_at)

    # Send CoAP to set override
    uri = get_device_uri(device_id)
    if uri:
        if status == "on":
            coap_payload = '{"mo": 1, "ls": 1}'
        elif status == "off":
            coap_payload = '{"mo": 1, "ls": 0}'
        else:
            coap_payload = '{"mo": 1}'

        if override_type == "permanent":
            coap_payload = coap_payload[:-1] + ', "od": 1576800000}'  # ~50 years

        asyncio.run(send_coap_request(uri, coap_payload))

    print(f"🎛️ Override set: {device_id} = {status} ({override_type})")
    logger.info(f"🎛️ Override set: {device_id} = {status} ({override_type}) via CoAP")

def process_sensor_data(device_id: str, payload: dict):
    """Process incoming sensor data with heating system focus"""
    try:
        # Validate input
        if not device_id or not isinstance(payload, dict):
            logger.warning(f"⚠️ Invalid sensor data: device_id={device_id}, payload={type(payload)}")
            return

        # Check clock synchronization status
        clock_synced = payload.get('clock_synced', 0)
        cycles_since_sync = payload.get('cycles_since_sync', 0)

        # Sync clock if not synced or drift detected (240 cycles = 1 hour)
        if clock_synced == 0 or cycles_since_sync >= 240:
            logger.info(f"⏰ Clock sync needed for {device_id}: synced={clock_synced}, cycles={cycles_since_sync}")
            # Schedule sync in background thread to avoid blocking
            import threading
            sync_thread = threading.Thread(
                target=lambda: asyncio.run(sync_device_clock(device_id)),
                daemon=True
            )
            sync_thread.start()

        # Create processed data with conversions - HEATING FOCUS
        # Handle temperature values that may be integers (from new node format)
        # Note: 0 is used as sentinel value for unset temperatures (changed from -1)
        predicted_temp = float(payload.get('predicted_temp', 0))
        target_temp = float(payload.get('target_temp', 0))

        # Ensure no negative values (legacy -1 values should be treated as 0)
        if predicted_temp < 0:
            predicted_temp = 0.0
        if target_temp < 0:
            target_temp = 0.0

        processed_data = {
            'device_id': device_id,
            'location': payload.get('location', 'unknown'),
            'lux': payload.get('lux', 0),
            'occupancy': payload.get('occupancy', 0),
            'temperature': payload.get('temperature', 0),
            'predicted_temp': predicted_temp,
            'target_temp': target_temp,
            'humidity': payload.get('humidity', 0),
            'co2': payload.get('co2', 400),
            'room_usage_wh': payload.get('room_usage_wh', 0),
            'heating_status': payload.get('heating_status', 0),  # Changed from led_status
            'manual_override': payload.get('manual_override', 0),
            'optimization_event': payload.get('optimization_event', 0),
            'sim_occupancy': payload.get('sim_occupancy', 0),
            'clock_synced': clock_synced,
            'day': payload.get('day', 0),
            'hour': payload.get('hour', 0),
            'minute': payload.get('minute', 0),
            'timestamp': datetime.now().isoformat()  # Convert datetime to ISO string for JSON serialization
        }

        # Extract IP address if provided in payload for dynamic URI mapping
        ip_address = payload.get('ip')
        if ip_address:
            # Construct CoAP URI from IP address
            processed_data['coap_uri'] = f"coap://[{ip_address}]/settings"
            logger.info(f"📡 Dynamic URI mapping for {device_id}: {processed_data['coap_uri']}")

        # Store in database
        db.store_sensor_data(device_id, processed_data)

        # Update latest data
        latest_sensor_data[device_id] = {
            **processed_data,
            'timestamp': processed_data['timestamp']  # Already converted to ISO string
        }

        # Check for override first
        override_status = check_device_override(device_id)
        if override_status:
            # Override is active - no need to send commands here since they were already sent in set_device_override()
            # Just log that override is active and return early
            reason = f"manual_override_{device_overrides[device_id]['type']}"
            logger.debug(f"🎛️ Override active: {device_id} = {override_status} ({reason}) - skipping sensor processing")
            return  # Exit early, override is already active

        # Manual-only mode - system does NOT make automatic heating control decisions
        # Temperature predictions and sensor data are stored and monitored
        # Heating control only happens via manual overrides through web UI
        logger.debug(f"📊 Sensor data processed for {device_id} (T: {processed_data['temperature']}°C, Pred: {processed_data['predicted_temp']}°C, Target: {processed_data['target_temp']}°C) - manual mode only")
        return

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

        try:
            logger.info(f"Raw payload bytes: {msg.payload}")
            logger.info(f"Payload as repr: {repr(msg.payload)}")

            # Decode payload to string
            payload_str = msg.payload.decode() if isinstance(msg.payload, bytes) else msg.payload

            # Try to parse JSON directly first
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError as e:
                # Attempt to repair malformed JSON with missing float values
                # Pattern: "field_name":, (missing value) -> "field_name":0.0,
                logger.warning(f"⚠️ Attempting to repair malformed JSON from {device_id}")

                # Fix missing float values (predicted_temp, target_temp, etc.)
                repaired_str = re.sub(r'("(?:predicted_temp|target_temp|temperature|humidity|co2)"\s*:\s*),', r'\g<1>0.0,', payload_str)
                repaired_str = re.sub(r'("(?:predicted_temp|target_temp|temperature|humidity|co2)"\s*:\s*)}', r'\g<1>0.0}', repaired_str)

                # Try parsing the repaired JSON
                try:
                    payload = json.loads(repaired_str)
                    logger.info(f"✅ Successfully repaired JSON for {device_id}")
                    logger.debug(f"   Original: {payload_str[:200]}")
                    logger.debug(f"   Repaired: {repaired_str[:200]}")
                except json.JSONDecodeError as e2:
                    # Still failed after repair attempt
                    logger.error(f"❌ JSON repair failed for topic {msg.topic}: {e2}")
                    logger.error(f"   Original error: {e}")
                    logger.error(f"   Raw payload: {msg.payload}")
                    logger.error(f"   Repaired attempt: {repaired_str[:200]}")
                    raise e  # Raise original error

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for topic {msg.topic}: {e}")
            logger.error(f"Raw payload: {msg.payload}")
            logger.error(f"Payload type: {type(msg.payload)}")
            logger.error(f"Payload length: {len(msg.payload) if hasattr(msg.payload, '__len__') else 'N/A'}")
            # Don't raise - just skip this message to prevent crash
            return

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
                # Set 24h override to "on" (since system stays put, button press means user wants lights on)
                set_device_override(device_id, "on", "24h")
                logger.info(f"🔘 Button press: {device_id} override set to on (24h)")
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

# Load border router mappings from database
border_router_neighbors = db.load_border_router_mappings()
print(f"🌐 Loaded {len(border_router_neighbors)} border router mappings from database")

last_neighbor_discovery = 0  # Timestamp of last discovery

async def validate_border_router_mappings():
    """
    Validate existing border router mappings by checking if devices are still reachable
    Removes mappings for devices that are no longer responding
    """
    global border_router_neighbors

    if not border_router_neighbors:
        return

    logger.info(f"🔍 Validating {len(border_router_neighbors)} border router mappings...")

    invalid_mappings = []

    for device_id, ip_addr in border_router_neighbors.items():
        try:
            # Quick CoAP ping to check if device is still reachable
            protocol = await Context.create_client_context(transports=['udp6'])
            request = Message(code=GET, uri=f"coap://[{ip_addr}]/settings")

            response = await asyncio.wait_for(
                protocol.request(request).response,
                timeout=2.0
            )

            if not response.code.is_successful():
                logger.warning(f"⚠️ Device {device_id} at {ip_addr} returned error code: {response.code}")
                invalid_mappings.append(device_id)
            else:
                logger.debug(f"✅ Device {device_id} at {ip_addr} is reachable")

        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Device {device_id} at {ip_addr} timed out")
            invalid_mappings.append(device_id)
        except Exception as e:
            logger.warning(f"⚠️ Device {device_id} at {ip_addr} unreachable: {e}")
            invalid_mappings.append(device_id)
        finally:
            try:
                await protocol.shutdown()
            except:
                pass

    # Remove invalid mappings
    if invalid_mappings:
        for device_id in invalid_mappings:
            del border_router_neighbors[device_id]
            logger.info(f"🗑️ Removed stale mapping for {device_id}")

        logger.info(f"🧹 Cleaned up {len(invalid_mappings)} invalid border router mappings")
    else:
        logger.debug("✅ All border router mappings are valid")

def discover_border_router_neighbors():
    """
    Discover neighboring nodes from border router's web interface
    Returns dict mapping device_ids to IP addresses
    Persists mappings to database for durability across restarts
    """
    global border_router_neighbors, last_neighbor_discovery

    # Check if requests is available
    if not REQUESTS_AVAILABLE:
        logger.warning("⚠️ Border router discovery unavailable - requests module not installed")
        return border_router_neighbors

    # Expected devices that should be discoverable
    expected_devices = {'node1', 'node2', 'node3'}

    # Check if we have mappings for all expected devices
    missing_devices = expected_devices - set(border_router_neighbors.keys())

    # Only rediscover if we have missing devices or it's been more than 5 minutes since last discovery
    current_time = time.time()
    should_discover = (
        len(missing_devices) > 0 or  # Missing some devices
        (current_time - last_neighbor_discovery) > 300  # 5 minutes since last discovery
    )

    if not should_discover:
        logger.debug(f"🌐 Using cached border router mappings: {border_router_neighbors}")
        return border_router_neighbors

    try:
        # Border router typically runs on fd00::f6ce:365a:bb21:6e94 (from tunslip6 configuration)
        border_router_url = "http://[fd00::f6ce:365a:bb21:6e94]/"

        logger.info("🔍 Discovering neighbors from border router...")
        response = requests.get(border_router_url, timeout=5)

        if response.status_code != 200:
            logger.warning(f"❌ Border router returned status {response.status_code}")
            return border_router_neighbors

        html_content = response.text
        logger.debug(f"📄 Border router response: {len(html_content)} chars")

        # Parse HTML for neighbor list
        # Look for: <li>fd00::f6ce:3673:822d:d8c7 (parent: fd00::f6ce:365a:bb21:6e94) 1500s</li>
        # We only want the IP address part before the space
        neighbor_ips = []
        import re
        li_pattern = r'<li>([0-9a-f:]+)\s'
        matches = re.findall(li_pattern, html_content)

        for ip in matches:
            # Skip the border router itself (fd00::f6ce:365a:bb21:6e94)
            if ip != "fd00::f6ce:365a:bb21:6e94":
                neighbor_ips.append(ip)

        logger.info(f"📡 Found {len(neighbor_ips)} neighbor IPs: {neighbor_ips}")

        # Query each IP to get device ID and create mapping
        device_mapping = {}
        new_mappings = 0

        for ip in neighbor_ips:
            logger.info(f"🔍 Querying device at {ip} for ID...")
            device_id = asyncio.run(query_device_id(ip))
            if device_id:
                device_mapping[device_id] = ip
                logger.info(f"🗺️ Mapped {device_id} -> {ip}")

                # Save to database if this is a new or changed mapping
                if device_id not in border_router_neighbors or border_router_neighbors[device_id] != ip:
                    db.save_border_router_mapping(device_id, ip)
                    new_mappings += 1
            else:
                logger.warning(f"⚠️ Could not identify device at {ip}")

        # Update global cache with new mappings
        border_router_neighbors.update(device_mapping)
        last_neighbor_discovery = current_time

        # Clean up stale mappings periodically (every hour)
        if current_time - getattr(discover_border_router_neighbors, '_last_cleanup', 0) > 3600:
            db.cleanup_stale_mappings()
            # Also validate current mappings
            asyncio.run(validate_border_router_mappings())
            discover_border_router_neighbors._last_cleanup = current_time

        if new_mappings > 0:
            logger.info(f"✅ Border router discovery complete: {len(device_mapping)} devices mapped, {new_mappings} new/updated")
        else:
            logger.debug(f"✅ Border router discovery complete: {len(device_mapping)} devices mapped (no changes)")

        return border_router_neighbors

    except Exception as e:
        logger.warning(f"❌ Border router discovery failed: {e}")
        return border_router_neighbors

# REST API Endpoints
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Check if the pool is initialized
        db_status = 'disconnected'
        if db.pool:
            try:
                # Try to get a connection to check pool health
                conn = db.pool.get_connection()
                db_status = 'connected'
                conn.close()
            except mysql.connector.Error:
                db_status = 'disconnected'

        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'database': db_status,
                'ml_model': 'disabled',  # ML no longer used for LED control decisions
                'mqtt': 'running',                'api': 'running'
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

        if db_status == 'disconnected':
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

    # Get all known devices from database (historical data)
    all_known_devices = db.get_device_locations_from_db()

    # For each known device, get the latest data if available
    for device_id in all_known_devices.keys():
        current_data = latest_sensor_data.get(device_id)
        override = device_overrides.get(device_id)

        devices[device_id] = {
            'latest_data': current_data if current_data else None,
            'uri': get_device_uri(device_id),
            'override': {
                'active': override is not None,
                'status': override['status'] if override else None,
                'type': override['type'] if override else None,
                'expires_at': override['expires_at'].isoformat() if override and override.get('expires_at') else None
            } if override else {'active': False}
        }

    # Also include any devices that are currently active but might not have location data
    for device_id, data in latest_sensor_data.items():
        if device_id not in devices:
            override = device_overrides.get(device_id)
            devices[device_id] = {
                'latest_data': data,
                'uri': get_device_uri(device_id),
                'override': {
                    'active': override is not None,
                    'status': override['status'] if override else None,
                    'type': override['type'] if override else None,
                    'expires_at': override['expires_at'].isoformat() if override and override.get('expires_at') else None
                } if override else {'active': False}
            }

    return jsonify(devices)

@app.route('/api/device-locations', methods=['GET'])
def get_device_locations():
    """Get device-to-location mapping for all known devices"""
    # Always get historical locations from database first
    locations = db.get_device_locations_from_db()

    # Then merge/override with current locations from active nodes
    for device_id, data in latest_sensor_data.items():
        location = data.get('location')
        if location:
            locations[device_id] = location

    return jsonify(locations)

@app.route('/api/devices/<device_id>/override', methods=['POST'])
def set_override(device_id):
    """Set device override"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    status = data.get('status')  # "on" or "off"
    override_type = data.get('type', '24h')  # "1h", "4h", "12h", "24h", "permanent", "disabled"

    if status not in ['on', 'off']:
        return jsonify({'error': 'Status must be "on" or "off"'}), 400

    if override_type not in ['1h', '4h', '12h', '24h', 'permanent', 'disabled']:
        return jsonify({'error': 'Type must be "1h", "4h", "12h", "24h", "permanent", or "disabled"'}), 400

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

@app.route('/api/devices/<device_id>/led', methods=['POST'])
def set_led_control(device_id):
    """Set LED control independently"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    status = data.get('status')  # "on" or "off"
    override_type = data.get('type', '24h')  # "1h", "4h", "12h", "24h", "permanent", "disabled"

    if status not in ['on', 'off']:
        return jsonify({'error': 'Status must be "on" or "off"'}), 400

    if override_type not in ['1h', '4h', '12h', '24h', 'permanent', 'disabled']:
        return jsonify({'error': 'Type must be "1h", "4h", "12h", "24h", "permanent", or "disabled"'}), 400

    # Send CoAP command for LED control
    uri = get_device_uri(device_id)
    if uri:
        led_value = 1 if status == "on" else 0
        coap_payload = f'{{"mo": 1, "ls": {led_value}}}'

        if override_type == "permanent":
            coap_payload = coap_payload[:-1] + ', "od": 1576800000}'  # ~50 years

        asyncio.run(send_coap_request(uri, coap_payload))
        logger.info(f"💡 LED control: {device_id} LED {status.upper()} ({override_type})")

    return jsonify({
        'success': True,
        'device_id': device_id,
        'control_type': 'led',
        'status': status,
        'type': override_type
    })

@app.route('/api/devices/<device_id>/heating', methods=['POST'])
def set_heating_control(device_id):
    """Set heating control independently"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    status = data.get('status')  # "on" or "off"
    override_type = data.get('type', '24h')  # "1h", "4h", "12h", "24h", "permanent", "disabled"

    if status not in ['on', 'off']:
        return jsonify({'error': 'Status must be "on" or "off"'}), 400

    if override_type not in ['1h', '4h', '12h', '24h', 'permanent', 'disabled']:
        return jsonify({'error': 'Type must be "1h", "4h", "12h", "24h", "permanent", or "disabled"'}), 400

    # Send CoAP command for heating control
    uri = get_device_uri(device_id)
    if uri:
        heating_value = 1 if status == "on" else 0
        coap_payload = f'{{"mo": 1, "hs": {heating_value}}}'

        if override_type == "permanent":
            coap_payload = coap_payload[:-1] + ', "od": 1576800000}'  # ~50 years

        asyncio.run(send_coap_request(uri, coap_payload))
        logger.info(f"🔥 Heating control: {device_id} HEATING {status.upper()} ({override_type})")

    return jsonify({
        'success': True,
        'device_id': device_id,
        'control_type': 'heating',
        'status': status,
        'type': override_type
    })

@app.route('/api/sensor-data', methods=['GET'])
def get_sensor_data():
    """Get recent sensor data"""
    hours = request.args.get('hours', 24, type=int)
    if hours is None:
        hours = 24

    # Get historical data from database
    historical_data = db.get_recent_data(hours)

    # Create a dict keyed by device_id for easy merging
    data_by_device = {}
    for entry in historical_data:
        device_id = entry['device_id']
        if device_id not in data_by_device:
            data_by_device[device_id] = []

        # Ensure timestamp is a string for consistent sorting
        timestamp = entry.get('timestamp')
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()
        elif not isinstance(timestamp, str):
            timestamp = str(timestamp)

        entry['timestamp'] = timestamp
        data_by_device[device_id].append(entry)

    # Add/merge current data from active nodes
    for device_id, current_data in latest_sensor_data.items():
        # Create an entry for current data
        timestamp = current_data.get('timestamp', datetime.now().isoformat())
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()
        elif not isinstance(timestamp, str):
            timestamp = str(timestamp)

        current_entry = {
            'device_id': device_id,
            'payload': current_data,
            'timestamp': timestamp
        }

        if device_id not in data_by_device:
            data_by_device[device_id] = []

        # Add current data (it will be the most recent)
        data_by_device[device_id].insert(0, current_entry)

    # Flatten back to list and sort by timestamp (most recent first)
    all_data = []
    for device_entries in data_by_device.values():
        all_data.extend(device_entries)

    # Sort by timestamp string (ISO format is lexicographically sortable)
    all_data.sort(key=lambda x: x['timestamp'], reverse=True)

    return jsonify(all_data)

@app.route('/api/energy-stats', methods=['GET'])
def get_energy_stats():
    """Get energy optimization statistics"""
    return jsonify(db.get_energy_stats())

@app.route('/api/baseline-comparison', methods=['GET'])
def get_baseline_comparison():
    """Get detailed baseline vs ML model comparison statistics"""
    # No automatic decisions are made, so baseline comparison is not applicable
    comparison_stats = {
        'note': 'System operates in manual-only mode. No automatic LED control decisions are made.',
        'baseline_assumption': 'N/A - No automatic control',
        'current_baseline_consumption_kw': 0.0,
        'rooms_currently_occupied': 0,
        'ml_energy_saved_vs_baseline_kwh': 0.0,
        'efficiency_improvement_percent': 0.0,
        'total_ml_decisions': 0,
        'total_system_decisions': 0,
        'ml_model_active': False,
        'energy_stats': db.get_energy_stats(),
        'calculation_timestamp': datetime.now().isoformat()
    }

    return jsonify(comparison_stats)

@app.route('/api/model-info', methods=['GET'])
def get_model_info():
    """Get ML model information and capabilities"""
    model_info = {
        'model_loaded': trained_model is not None,
        'model_type': 'disabled',  # ML no longer used for LED control decisions
        'decision_method': 'manual_only',  # Only manual overrides control LEDs
        'energy_efficiency': 'N/A',  # No automatic energy optimization
        'accuracy': 'N/A',
        'features_available': feature_stats is not None,
        'feature_count': 0,  # Not used for decisions
        'expected_features': [],
        'energy_saving_rules': {},
        'training_info': {},
        'note': 'System operates in manual-only mode. No automatic LED control decisions are made.'
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
        # Publish global command for virtual nodes
        global_topic = "devices/all/control"
        publish.single(global_topic, json.dumps({"command": command}),
                      hostname=MQTT_BROKER, port=MQTT_PORT)

        # Also send global command for physical nodes via serial bridge
        logger.info(f"🌐 Sending global command {command} to all devices")

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

@app.route('/api/devices/all/led', methods=['POST'])
def global_led_control():
    """Control LEDs on all devices"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        status = data.get('status')  # "on" or "off"
        override_type = data.get('type', '24h')

        if status not in ['on', 'off']:
            return jsonify({'error': 'Status must be "on" or "off"'}), 400

        # Get all known devices from latest sensor data
        devices = list(latest_sensor_data.keys())

        for device_id in devices:
            uri = get_device_uri(device_id)
            if uri:
                led_value = 1 if status == "on" else 0
                coap_payload = f'{{"mo": 1, "ls": {led_value}}}'
                asyncio.run(send_coap_request(uri, coap_payload))

        logger.info(f"💡 Global LED control: All devices LED {status.upper()}")

        return jsonify({
            'success': True,
            'message': f'LED {status.upper()} sent to {len(devices)} devices',
            'devices': devices
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/devices/all/led/auto', methods=['POST'])
def global_led_auto():
    """Set all LEDs to auto mode"""
    try:
        devices = list(latest_sensor_data.keys())

        for device_id in devices:
            uri = get_device_uri(device_id)
            if uri:
                coap_payload = '{"mo": 0, "ab": 1}'  # Disable manual override, enable auto
                asyncio.run(send_coap_request(uri, coap_payload))

        logger.info(f"🤖 Global LED auto mode: All devices")

        return jsonify({
            'success': True,
            'message': f'LED auto mode enabled for {len(devices)} devices',
            'devices': devices
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/devices/all/heating', methods=['POST'])
def global_heating_control():
    """Control heating on all devices"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        status = data.get('status')  # "on" or "off"
        override_type = data.get('type', '24h')

        if status not in ['on', 'off']:
            return jsonify({'error': 'Status must be "on" or "off"'}), 400

        # Get all known devices from latest sensor data
        devices = list(latest_sensor_data.keys())

        for device_id in devices:
            uri = get_device_uri(device_id)
            if uri:
                heating_value = 1 if status == "on" else 0
                coap_payload = f'{{"mo": 1, "hs": {heating_value}}}'
                asyncio.run(send_coap_request(uri, coap_payload))

        logger.info(f"🔥 Global heating control: All devices HEATING {status.upper()}")

        return jsonify({
            'success': True,
            'message': f'Heating {status.upper()} sent to {len(devices)} devices',
            'devices': devices
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/devices/all/heating/auto', methods=['POST'])
def global_heating_auto():
    """Set all heating to auto mode"""
    try:
        devices = list(latest_sensor_data.keys())

        for device_id in devices:
            uri = get_device_uri(device_id)
            if uri:
                coap_payload = '{"mo": 0, "ab": 1}'  # Disable manual override, enable auto
                asyncio.run(send_coap_request(uri, coap_payload))

        logger.info(f"🤖 Global heating auto mode: All devices")

        return jsonify({
            'success': True,
            'message': f'Heating auto mode enabled for {len(devices)} devices',
            'devices': devices
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/historical/clear', methods=['POST'])
def clear_historical_data():
    """Clear all historical sensor data from the database and reset statistics"""
    try:
        deleted_count = 0
        conn = db.get_connection()
        cursor = conn.cursor()

        # Count records before deletion
        cursor.execute("SELECT COUNT(*) FROM sensor_data")
        count_result = cursor.fetchone()
        deleted_count = count_result[0] if count_result else 0

        # Delete all historical sensor data
        cursor.execute("DELETE FROM sensor_data")

        # Reset energy statistics to zero
        cursor.execute("""
            UPDATE energy_stats
            SET total_decisions = 0,
                energy_saved = 0.000,
                ambient_overrides = 0,
                optimization_events = 0,
                baseline_energy = 0.000,
                ml_energy = 0.000
            WHERE id = 1
        """)

        conn.commit()

        # Clear in-memory cache
        global latest_sensor_data
        latest_sensor_data.clear()

        print(f"🗑️ Cleared {deleted_count} historical records from database")
        print(f"🔄 Reset energy statistics to zero")
        print(f"💾 Cleared in-memory sensor data cache")

        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'deleted_records': deleted_count,
            'message': f'Successfully deleted {deleted_count} historical records and reset all statistics'
        })
    except Exception as e:
        print(f"❌ Error clearing historical data: {e}")
        log_critical_error("db_errors", Exception(f"Failed to clear historical data: {e}"))
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/clock_sync', methods=['POST'])
def force_clock_sync():
    """Force clock synchronization for all connected devices"""
    try:
        synced_devices = []
        failed_devices = []

        # Discover border router neighbors to ensure we have the latest devices
        discover_border_router_neighbors()

        # Get all known devices from both sensor data and border router mappings
        devices = list(set(latest_sensor_data.keys()) | set(border_router_neighbors.keys()))
        
        if not devices:
            return jsonify({
                'success': False,
                'error': 'No devices available for synchronization'
            }), 404

        logger.info(f"🕐 Manual clock sync triggered for {len(devices)} device(s)")

        # Synchronize each device
        for device_id in devices:
            try:
                # Run async sync in event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success = loop.run_until_complete(sync_device_clock(device_id))
                loop.close()

                if success:
                    synced_devices.append(device_id)
                    logger.info(f"✅ Successfully synced {device_id}")
                else:
                    failed_devices.append(device_id)
                    logger.warning(f"⚠️ Failed to sync {device_id}")
            except Exception as e:
                failed_devices.append(device_id)
                logger.error(f"❌ Error syncing {device_id}: {e}")

        # Return results
        if len(synced_devices) > 0:
            return jsonify({
                'success': True,
                'synced_devices': len(synced_devices),
                'failed_devices': failed_devices,
                'message': f'Synchronized {len(synced_devices)} device(s)'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to sync any devices',
                'failed_devices': failed_devices
            }), 500

    except Exception as e:
        logger.error(f"❌ Error in manual clock sync: {e}")
        log_critical_error("clock_sync", e, "Manual clock sync failed")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/schedule/<device_id>', methods=['GET'])
def get_device_schedule(device_id):
    """Get temperature schedule for a device"""
    try:
        # For now, return a default schedule or fetch from CoAP
        # In a real implementation, this would query the device's /schedule endpoint
        uri = get_device_uri(device_id)
        if not uri:
            return jsonify({'success': False, 'error': 'Device URI not found'}), 404

        schedule_uri = uri.replace('/settings', '/schedule')

        # TODO: Implement CoAP GET request to fetch schedule
        # For now, return success with placeholder
        return jsonify({
            'success': True,
            'device_id': device_id,
            'message': 'Schedule endpoint available'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/schedule/<device_id>', methods=['POST'])
def update_device_schedule(device_id):
    """Update temperature schedule for a device - saves to DB and broadcasts to node"""
    try:
        data = request.get_json()
        if not data or 'schedule' not in data:
            return jsonify({'success': False, 'error': 'No schedule data provided'}), 400

        schedule = data['schedule']

        # Validate schedule (should be 168 temperature values)
        if not isinstance(schedule, list) or len(schedule) != 168:
            return jsonify({'success': False, 'error': 'Schedule must contain exactly 168 values (7 days * 24 hours)'}), 400

        # Save schedule to database FIRST (persistence)
        db.save_device_schedule(device_id, schedule)
        logger.info(f"💾 Schedule saved to database for {device_id}")

        # Get device URI
        uri = get_device_uri(device_id)
        if not uri:
            logger.error(f"❌ Device URI not found for {device_id}")
            # Schedule is saved to DB, but device is offline - will be broadcast when device comes online
            return jsonify({
                'success': True,
                'device_id': device_id,
                'message': 'Schedule saved to database (device offline - will broadcast when available)',
                'saved_to_db': True,
                'broadcast_success': False
            }), 200

        schedule_uri = uri.replace('/settings', '/schedule')
        logger.info(f"📅 Sending schedule to {device_id} at {schedule_uri}")

        # Optimize schedule data: convert floats to ints to reduce payload size
        # 20.0 -> 20, 0.0 -> 0, etc. (saves ~1/3 of the payload size)
        optimized_schedule = [int(temp) if temp == int(temp) else temp for temp in schedule]

        # Send CoAP PUT request with schedule (compact JSON, no spaces)
        coap_payload = json.dumps({'schedule': optimized_schedule}, separators=(',', ':'))

        logger.info(f"📦 Payload size: {len(coap_payload)} bytes (optimized)")

        try:
            response = asyncio.run(send_coap_request(schedule_uri, coap_payload))

            if response is None:
                logger.error(f"❌ Failed to send schedule to {device_id} - No CoAP response")
                return jsonify({
                    'success': False,
                    'error': 'Failed to communicate with device (CoAP timeout or unreachable)'
                }), 500

            logger.info(f"✅ Schedule successfully sent to {device_id}, response: {response}")

            # Update last_broadcast timestamp in database
            db.update_schedule_broadcast_time(device_id)

            return jsonify({
                'success': True,
                'device_id': device_id,
                'message': 'Temperature schedule updated successfully',
                'saved_to_db': True,
                'broadcast_success': True
            })
        except Exception as coap_error:
            logger.error(f"❌ CoAP error sending schedule to {device_id}: {coap_error}")
            return jsonify({
                'success': False,
                'error': f'CoAP communication error: {str(coap_error)}'
            }), 500
    except Exception as e:
        logger.error(f"❌ Failed to update schedule for {device_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/heating/<device_id>/control', methods=['POST'])
def control_heating(device_id):
    """Manual heating control - override automatic system"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400

        heating_command = data.get('command')  # 'on' or 'off'
        override_duration = data.get('duration', '24h')  # Default 24h override

        if heating_command not in ['on', 'off']:
            return jsonify({'success': False, 'error': 'Invalid heating command'}), 400

        # Set override with heating command
        set_device_override(device_id, heating_command, override_duration)

        return jsonify({
            'success': True,
            'device_id': device_id,
            'command': heating_command,
            'duration': override_duration,
            'message': f'Heating {heating_command} for {override_duration}'
        })
    except Exception as e:
        logger.error(f"❌ Failed to control heating for {device_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/schedules', methods=['GET'])
def get_all_schedules():
    """Get all saved temperature schedules"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, name, description, created_at, updated_at
            FROM temperature_schedules
            ORDER BY created_at DESC
        """)

        schedules = cursor.fetchall()

        return jsonify({
            'success': True,
            'schedules': schedules
        })
    except Exception as e:
        logger.error(f"❌ Failed to fetch schedules: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/history/<device_id>', methods=['GET'])
def get_historical_data(device_id):
    """Get last 48 temperature readings (24 hours at 30-min intervals) for device initialization"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Get last 48 temperature readings from sensor_data
        # Assuming data is stored every 15 seconds, we want readings from last 24 hours
        # For 30-min intervals, we need readings at 0, 30, 60, 90 minutes, etc.
        cursor.execute("""
            SELECT payload, timestamp
            FROM sensor_data
            WHERE device_id = %s
            AND timestamp >= NOW() - INTERVAL 24 HOUR
            ORDER BY timestamp DESC
        """, (device_id,))

        all_data = cursor.fetchall()

        # Extract temperatures and sample every 30 minutes (roughly)
        temperatures = []
        last_time = None

        for row in reversed(all_data):  # Process oldest to newest
            try:
                payload = json.loads(row['payload']) if isinstance(row['payload'], str) else row['payload']
                temp = payload.get('temperature', 20)
                timestamp = row['timestamp']

                # Add reading if it's the first one or 30+ minutes since last
                if last_time is None or (timestamp - last_time).total_seconds() >= 1800:
                    temperatures.append(temp)
                    last_time = timestamp

                    if len(temperatures) >= TEMP_HISTORY_SIZE:
                        break
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to parse temperature from payload: {e}")
                continue

        # Fill remaining slots with 20°C if we don't have enough data
        while len(temperatures) < TEMP_HISTORY_SIZE:
            temperatures.insert(0, 20)  # Prepend 20°C for older missing data

        # Ensure we have exactly 48 readings
        temperatures = temperatures[:TEMP_HISTORY_SIZE]

        # Get current server time for clock sync
        now = datetime.now()

        response = {
            "temps": [int(t * 10) for t in temperatures],  # Send as int*10 for precision
            "day": now.weekday(),  # 0=Monday, 6=Sunday
            "hour": now.hour,
            "minute": now.minute,
            "count": len([t for t in temperatures if t != 20])  # Count non-default values
        }

        logger.info(f"⏰ Historical data request for {device_id}: {response['count']}/48 real readings")

        return jsonify(response)

    except Exception as e:
        log_critical_error("api", e, f"Failed to fetch historical data for {device_id}")
        # Return defaults on error so node can still initialize
        now = datetime.now()
        return jsonify({
            "temps": [200] * TEMP_HISTORY_SIZE,  # 20.0°C * 10
            "day": now.weekday(),
            "hour": now.hour,
            "minute": now.minute,
            "count": 0
        })
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route('/api/schedules/<int:schedule_id>', methods=['GET'])
def get_schedule_by_id(schedule_id):
    """Get specific schedule by ID"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, name, description, schedule_data, created_at, updated_at
            FROM temperature_schedules
            WHERE id = %s
        """, (schedule_id,))

        schedule = cursor.fetchone()

        if not schedule:
            return jsonify({'success': False, 'error': 'Schedule not found'}), 404

        # Parse JSON schedule data
        schedule['schedule_data'] = json.loads(schedule['schedule_data'])

        return jsonify({
            'success': True,
            'schedule': schedule
        })
    except Exception as e:
        logger.error(f"❌ Failed to fetch schedule {schedule_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/schedules', methods=['POST'])
def create_schedule():
    """Create new temperature schedule"""
    try:
        data = request.get_json()

        if not data or 'name' not in data or 'schedule' not in data:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400

        name = data['name']
        description = data.get('description', '')
        schedule = data['schedule']

        # Validate schedule
        if not isinstance(schedule, list) or len(schedule) != 168:
            return jsonify({
                'success': False,
                'error': 'Schedule must contain exactly 168 values (7 days * 24 hours)'
            }), 400

        conn = db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO temperature_schedules (name, description, schedule_data)
            VALUES (%s, %s, %s)
        """, (name, description, json.dumps(schedule)))

        schedule_id = cursor.lastrowid

        logger.info(f"💾 Created new schedule: {name} (ID: {schedule_id})")

        return jsonify({
            'success': True,
            'schedule_id': schedule_id,
            'message': f'Schedule "{name}" created successfully'
        })
    except Exception as e:
        logger.error(f"❌ Failed to create schedule: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/schedules/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    """Delete temperature schedule"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM temperature_schedules
            WHERE id = %s
        """, (schedule_id,))

        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Schedule not found'}), 404

        logger.info(f"🗑️ Deleted schedule ID: {schedule_id}")

        return jsonify({
            'success': True,
            'message': 'Schedule deleted successfully'
        })
    except Exception as e:
        logger.error(f"❌ Failed to delete schedule {schedule_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

def periodic_border_router_discovery():
    """Background thread to periodically discover border router neighbors"""
    logger.info("🌐 Starting periodic border router discovery thread...")
    while True:
        try:
            # Discover neighbors every 5 minutes
            time.sleep(300)
            logger.info("🔍 Running periodic border router discovery...")
            discover_border_router_neighbors()
        except Exception as e:
            log_critical_error("discovery", e, "Periodic border router discovery failed")
            time.sleep(10)  # Wait 10 seconds before retrying on error

def periodic_schedule_broadcast():
    """Background thread that broadcasts schedules to devices on first contact and periodically (every 5 minutes)"""
    logger.info("📅 Starting periodic schedule broadcast thread...")
    BROADCAST_INTERVAL = 300  # 5 minutes in seconds

    # Wait initial 20 seconds for system to stabilize
    time.sleep(20)

    while True:
        try:
            time.sleep(60)  # Check every minute for new devices, broadcast every 5 minutes

            # Get devices that need schedule broadcast (first time or periodic refresh)
            devices_needing_broadcast = db.get_devices_needing_schedule_broadcast(BROADCAST_INTERVAL)

            if devices_needing_broadcast:
                logger.info("\n" + "="*60)
                logger.info("📅 PERIODIC SCHEDULE BROADCAST")
                logger.info("="*60)
                logger.info(f"  Devices needing schedule broadcast: {devices_needing_broadcast}")

                for device_id in devices_needing_broadcast:
                    # Check if device is reachable
                    uri = get_device_uri(device_id)
                    if not uri:
                        logger.warning(f"  ⚠️ {device_id}: Device URI not found (offline?)")
                        continue

                    # Load schedule from database
                    schedule = db.load_device_schedule(device_id)
                    if not schedule:
                        logger.warning(f"  ⚠️ {device_id}: No schedule found in database")
                        continue

                    # Broadcast schedule to device
                    logger.info(f"  📡 Broadcasting schedule to {device_id}...")
                    schedule_uri = uri.replace('/settings', '/schedule')

                    # Optimize schedule data
                    optimized_schedule = [int(temp) if temp == int(temp) else temp for temp in schedule]
                    coap_payload = json.dumps({'schedule': optimized_schedule}, separators=(',', ':'))

                    try:
                        response = asyncio.run(send_coap_request(schedule_uri, coap_payload))
                        if response is not None:
                            logger.info(f"  ✅ {device_id}: Schedule broadcast successful")
                            db.update_schedule_broadcast_time(device_id)
                        else:
                            logger.error(f"  ❌ {device_id}: Schedule broadcast failed (no response)")
                    except Exception as coap_error:
                        logger.error(f"  ❌ {device_id}: Schedule broadcast error: {coap_error}")

                    time.sleep(0.5)  # Small delay between devices

                logger.info("="*60 + "\n")

        except Exception as e:
            logger.error(f"❌ Error in periodic schedule broadcast: {e}")
            time.sleep(60)  # Wait 1 minute before retry on error

def periodic_time_sync_broadcast():
    """Background thread to periodically broadcast time sync to all nodes"""
    logger.info("⏰ Starting periodic time sync broadcast thread...")

    # Wait initial 30 seconds for system to stabilize
    time.sleep(30)

    while True:
        try:
            # Broadcast time sync every hour (3600 seconds)
            logger.info("⏰ Broadcasting time sync to all nodes...")

            # Discover border router neighbors to ensure we have the latest devices
            discover_border_router_neighbors()

            # Get all known device IDs from latest sensor data and border router mappings
            all_device_ids = set(latest_sensor_data.keys()) | set(border_router_neighbors.keys())

            if not all_device_ids:
                logger.debug("⏰ No devices to sync - will retry in 1 hour")
            else:
                logger.info(f"⏰ Syncing {len(all_device_ids)} devices: {', '.join(all_device_ids)}")

                # Sync each device
                for device_id in all_device_ids:
                    try:
                        asyncio.run(sync_device_clock(device_id))
                        # Small delay between devices to avoid flooding
                        time.sleep(1)
                    except Exception as e:
                        logger.error(f"⏰ Failed to sync {device_id}: {e}")

                logger.info(f"✅ Time sync broadcast complete for {len(all_device_ids)} devices")

            # Wait 30 seconds before next broadcast
            time.sleep(30)

        except Exception as e:
            log_critical_error("time_sync", e, "Periodic time sync broadcast failed")
            time.sleep(60)  # Wait 1 minute before retrying on error

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
                logger.info(f"⏳ Retrying MQTT connection in 5 seconds...")
                time.sleep(5)
            else:
                logger.error("💥 MQTT connection failed after multiple retries. Exiting MQTT thread.")
                break # Exit loop

        except Exception as e:
            retry_count += 1
            log_critical_error("mqtt", e, f"MQTT client error (attempt {retry_count})")
            if retry_count < max_retries:
                logger.info(f"⏳ Retrying MQTT connection in 5 seconds...")
                time.sleep(5)
            else:
                logger.error("💥 MQTT client error after multiple retries. Exiting MQTT thread.")
                break # Exit loop

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

        # The DatabaseManager now handles connection retries internally.
        # We just need to check if the pool was successfully created.
        if not db.pool:
            logger.error("💥 STARTUP FAILED: Database connection pool unavailable.")
            sys.exit(1)

        # Do initial border router discovery
        logger.info("🔍 Performing initial border router discovery...")
        discover_border_router_neighbors()

        # Start periodic border router discovery in background thread
        logger.info("🌐 Starting periodic border router discovery thread...")
        discovery_thread = threading.Thread(target=periodic_border_router_discovery, daemon=True)
        discovery_thread.start()

        # Start periodic time sync broadcast in background thread
        logger.info("⏰ Starting periodic time sync broadcast thread...")
        time_sync_thread = threading.Thread(target=periodic_time_sync_broadcast, daemon=True)
        time_sync_thread.start()

        # Start periodic schedule broadcast in background thread
        logger.info("📅 Starting periodic schedule broadcast thread...")
        schedule_broadcast_thread = threading.Thread(target=periodic_schedule_broadcast, daemon=True)
        schedule_broadcast_thread.start()

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