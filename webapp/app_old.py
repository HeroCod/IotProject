#!/usr/bin/env python3
"""
Real-Time IoT Energy Monitoring Web Application
SOLO PROJECT - Flask-based dashboard for live sensor monitoring

Features:
- Real-time sensor data visualization
- Energy optimization tracking
- Manual LED control via web interface
- Historical data charts
- System status monitoring
- MQTT integration for live updates
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import mysql.connector
import json
import threading
import time
from datetime import datetime, timedelta
import os
from typing import Dict, List, Optional, Union, Any
import logging
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'energy-iot-secret-key-2025'
socketio = SocketIO(app, cors_allowed_origins="*")

# Configuration
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))

MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_USER = os.environ.get("MYSQL_USER", "iotuser")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "iotpass")
MYSQL_DB = os.environ.get("MYSQL_DB", "iotdb")

# Global data storage for real-time updates
latest_sensor_data = {}
energy_stats = {
    'total_consumption': 0.0,
    'energy_saved': 0.0,
    'optimization_events': 0,
    'manual_overrides': 0
}
system_status = {
    'nodes_online': 0,
    'last_update': None,
    'mqtt_connected': False,
    'db_connected': False
}

class IoTDataCollector:
    def __init__(self):
        self.mqtt_client = None
        self.db_connection = None
        self.setup_database()
        self.setup_mqtt()
        
    def setup_database(self):
        """Initialize database connection and create tables if needed"""
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                self.db_connection = mysql.connector.connect(
                    host=MYSQL_HOST,
                    user=MYSQL_USER,
                    password=MYSQL_PASSWORD,
                    database=MYSQL_DB,
                    autocommit=True,
                    reconnect=True
                )
                
                # Test connection
                if self.db_connection.is_connected():
                    # Create sensor_data table if it doesn't exist
                    cursor = self.db_connection.cursor()
                    create_table_query = """
                    CREATE TABLE IF NOT EXISTS sensor_data (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        device_id VARCHAR(50) NOT NULL,
                        payload JSON NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_device_time (device_id, timestamp),
                        INDEX idx_timestamp (timestamp)
                    )
                    """
                    cursor.execute(create_table_query)
                    cursor.close()
                    
                    system_status['db_connected'] = True
                    logger.info("✅ Database connected and tables initialized")
                    return
                    
            except mysql.connector.Error as e:
                logger.error(f"❌ Database connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error("❌ All database connection attempts failed")
                    system_status['db_connected'] = False
                    self.db_connection = None
            
    def setup_mqtt(self):
        """Initialize MQTT client and connect to broker"""
        import uuid
        # Use unique client ID to avoid conflicts
        client_id = f"webapp_{uuid.uuid4().hex[:8]}"
        self.mqtt_client = mqtt.Client(client_id=client_id)
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        
        # Set reasonable timeouts
        self.mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, 60)
        self.mqtt_client.loop_start()
        logger.info(f"✅ MQTT client started with ID: {client_id}")
        
        # Wait a bit for initial connection
        time.sleep(2)
            
    def on_mqtt_connect(self, client, userdata, flags, rc):
        """Callback for MQTT connection"""
        if rc == 0:
            system_status['mqtt_connected'] = True
            logger.info("✅ Connected to MQTT broker")
            
            # Subscribe to all sensor topics
            client.subscribe("sensors/+/data")
            client.subscribe("sensors/+/button")
            logger.info("📡 Subscribed to sensor data topics")
        else:
            system_status['mqtt_connected'] = False
            logger.error(f"❌ MQTT connection failed with code {rc}")
            
    def on_mqtt_disconnect(self, client, userdata, rc):
        """Callback for MQTT disconnection"""
        system_status['mqtt_connected'] = False
        logger.warning(f"⚠️ MQTT disconnected with code {rc}")
        
        # Attempt reconnection if not a clean disconnect
        if rc != 0:
            logger.info("🔄 Attempting MQTT reconnection...")
            try:
                client.reconnect()
            except Exception as e:
                logger.error(f"❌ MQTT reconnection failed: {e}")
            
    def on_mqtt_message(self, client, userdata, msg):
        """Process incoming MQTT messages"""
        try:
            topic_parts = msg.topic.split('/')
            device_id = topic_parts[1]  # Extract device ID from topic
            message_type = topic_parts[2]  # data or button
            
            payload = json.loads(msg.payload.decode())
            timestamp = datetime.now()
            
            # Store in database
            if self.db_connection:
                self.store_sensor_data(device_id, payload, timestamp)
            
            # Update real-time data
            latest_sensor_data[device_id] = {
                'data': payload,
                'timestamp': timestamp.isoformat(),
                'type': message_type
            }
            
            # Update system status
            system_status['last_update'] = timestamp.isoformat()
            system_status['nodes_online'] = len(latest_sensor_data)
            
            # Update energy statistics
            self.update_energy_stats(payload)
            
            # Emit real-time update to web clients
            socketio.emit('sensor_update', {
                'device_id': device_id,
                'data': payload,
                'timestamp': timestamp.isoformat(),
                'type': message_type
            })
            
            logger.info(f"📊 {device_id}: {message_type} data processed")
            
        except Exception as e:
            logger.error(f"❌ Error processing MQTT message: {e}")
            
    def store_data(self, device_id: str, payload: dict):
        """Store data in database with connection recovery"""
        try:
            # Check if connection is alive
            if not self.db_connection or not self.db_connection.is_connected():
                logger.warning("Database connection lost, attempting to reconnect...")
                self.setup_database()
                
            if self.db_connection and self.db_connection.is_connected():
                cursor = self.db_connection.cursor()
                query = """
                INSERT INTO sensor_data (device_id, payload) 
                VALUES (%s, %s)
                """
                cursor.execute(query, (device_id, json.dumps(payload)))
                cursor.close()
                logger.debug(f"Data stored for device {device_id}")
            else:
                logger.error("❌ Unable to store data - no database connection")
                
        except mysql.connector.Error as e:
            logger.error(f"❌ Database error: {e}")
            # Try to reconnect
            self.setup_database()
        except Exception as e:
            logger.error(f"❌ Unexpected error storing data: {e}")

    def get_recent_data(self, limit: int = 100) -> List[dict]:
        """Get recent sensor data with proper type handling"""
        if not self.db_connection or not self.db_connection.is_connected():
            logger.warning("Database connection lost, attempting to reconnect...")
            self.setup_database()
            
        if not self.db_connection or not self.db_connection.is_connected():
            logger.error("❌ No database connection available")
            return []
            
        try:
            cursor = self.db_connection.cursor()
            query = """
            SELECT device_id, payload, timestamp 
            FROM sensor_data 
            ORDER BY timestamp DESC 
            LIMIT %s
            """
            cursor.execute(query, (limit,))
            
            results = []
            for row in cursor.fetchall():
                device_id, payload_str, timestamp = row
                
                try:
                    # Ensure payload_str is actually a string
                    if isinstance(payload_str, str):
                        payload = json.loads(payload_str)
                    elif isinstance(payload_str, bytes):
                        payload = json.loads(payload_str.decode('utf-8'))
                    else:
                        # Handle case where payload might be other type
                        payload = json.loads(str(payload_str))
                        
                    # Convert timestamp to string safely - avoid type checker issues
                    timestamp_str = str(timestamp)
                        
                    results.append({
                        'device_id': str(device_id),
                        'payload': payload,
                        'timestamp': timestamp_str
                    })
                except Exception as e:
                    logger.error(f"Error processing row data: {e}")
                    continue
                    
            cursor.close()
            return results
            
        except mysql.connector.Error as e:
            logger.error(f"❌ Database query error: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected error getting data: {e}")
            return []

    def store_sensor_data(self, device_id: str, payload: dict, timestamp: Optional[datetime] = None):
        """Store sensor data in database"""
        self.store_data(device_id, payload)

    def update_energy_stats(self, payload: Dict):
        """Update energy consumption and optimization statistics"""
        global energy_stats
        
        if 'room_usage' in payload:
            energy_stats['total_consumption'] += float(payload['room_usage'])
            
        if payload.get('energy_saving_mode') == 1:
            energy_stats['optimization_events'] += 1
            energy_stats['energy_saved'] += 0.05  # Estimated savings per event
            
        if payload.get('manual_override') == 1:
            energy_stats['manual_overrides'] += 1
            
    def send_led_command(self, device_id: str, command: str):
        """Send LED control command via MQTT"""
        if self.mqtt_client and system_status['mqtt_connected']:
            topic = f"actuators/{device_id}/led"
            self.mqtt_client.publish(topic, command)
            logger.info(f"💡 Sent {command} command to {device_id}")
            return True
        return False
        
    def get_historical_data(self, hours: int = 24) -> List[Dict]:
        """Retrieve historical sensor data from database"""
        if not self.db_connection:
            return []
            
        try:
            cursor = self.db_connection.cursor()
            since_time = datetime.now() - timedelta(hours=hours)
            
            query = """
            SELECT device_id, payload, timestamp 
            FROM sensor_data 
            WHERE timestamp >= %s 
            ORDER BY timestamp DESC 
            LIMIT 1000
            """
            
            cursor.execute(query, (since_time,))
            results = cursor.fetchall()
            cursor.close()
            
            historical_data = []
            for device_id, payload_str, timestamp in results:
                try:
                    # Ensure payload_str is actually a string
                    if isinstance(payload_str, str):
                        payload = json.loads(payload_str)
                    elif isinstance(payload_str, bytes):
                        payload = json.loads(payload_str.decode('utf-8'))
                    else:
                        # Handle case where payload might be other type
                        payload = json.loads(str(payload_str))
                        
                    # Convert timestamp to string safely - avoid type checker issues  
                    timestamp_str = str(timestamp)
                        
                    historical_data.append({
                        'device_id': str(device_id),
                        'data': payload,
                        'timestamp': timestamp_str
                    })
                except Exception as e:
                    logger.error(f"Error processing historical data row: {e}")
                    continue
                    
            return historical_data
            
        except mysql.connector.Error as e:
            logger.error(f"❌ Database query failed: {e}")
            return []

# Initialize data collector
data_collector = IoTDataCollector()

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/status')
def api_status():
    """API endpoint for system status"""
    return jsonify({
        'system_status': system_status,
        'energy_stats': energy_stats,
        'nodes_online': len(latest_sensor_data),
        'latest_data': latest_sensor_data
    })

@app.route('/api/historical/<int:hours>')
def api_historical(hours):
    """API endpoint for historical data"""
    historical_data = data_collector.get_historical_data(hours)
    return jsonify({
        'data': historical_data,
        'count': len(historical_data)
    })

@app.route('/api/control/<device_id>/<command>', methods=['POST'])
def api_control(device_id, command):
    """API endpoint for LED control"""
    if command not in ['on', 'off']:
        return jsonify({'error': 'Invalid command'}), 400
        
    success = data_collector.send_led_command(device_id, command)
    
    if success:
        return jsonify({
            'success': True,
            'message': f'Command {command} sent to {device_id}'
        })
    else:
        return jsonify({
            'success': False,
            'error': 'MQTT not connected'
        }), 500

@app.route('/control')
def control_panel():
    """Device control panel page"""
    return render_template('control.html', devices=latest_sensor_data.keys())

@app.route('/analytics')
def analytics():
    """Energy analytics page"""
    return render_template('analytics.html')

@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    logger.info("🔌 Client connected to WebSocket")
    emit('system_status', {
        'system_status': system_status,
        'energy_stats': energy_stats,
        'latest_data': latest_sensor_data
    })

@socketio.on('request_control')
def handle_control_request(data):
    """Handle LED control request via WebSocket"""
    device_id = data.get('device_id')
    command = data.get('command')
    
    if device_id and command in ['on', 'off']:
        success = data_collector.send_led_command(device_id, command)
        emit('control_response', {
            'device_id': device_id,
            'command': command,
            'success': success
        })

def run_webapp(host='0.0.0.0', port=5000, debug=False):
    """Run the Flask webapp"""
    logger.info(f"🚀 Starting IoT Energy Monitoring Webapp on {host}:{port}")
    socketio.run(app, host=host, port=port, debug=debug)

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='IoT Energy Monitoring Webapp')
    parser.add_argument('--host', default='0.0.0.0', help='Host address')
    parser.add_argument('--port', type=int, default=5000, help='Port number')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    run_webapp(host=args.host, port=args.port, debug=args.debug)
