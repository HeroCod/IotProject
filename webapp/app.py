#!/usr/bin/env python3
"""
IoT Energy Management System - Web Frontend
=============================================

Cloud-ready web application that communicates with the controller
via REST API calls. Designed for remote deployment.

Features:
- Device control and monitoring
- Real-time sensor data updates  
- 24h override system management
- Energy analytics dashboard
- WebSocket real-time updates
"""

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import requests
import json
import threading
import time
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'iot_webapp_secret_key_2024'
socketio = SocketIO(app, cors_allowed_origins="*")

# Controller API configuration
CONTROLLER_API_BASE = 'http://controller:5001/api'
CONTROLLER_API_LOCAL = 'http://localhost:5001/api'  # For local development

def call_controller_api(endpoint, method='GET', data=None):
    """Make REST API call to controller service"""
    try:
        # Try controller service first (Docker network)
        url = f"{CONTROLLER_API_BASE}/{endpoint}"
        
        if method == 'GET':
            response = requests.get(url, timeout=5)
        elif method == 'POST':
            response = requests.post(url, json=data, timeout=5)
        elif method == 'DELETE':
            response = requests.delete(url, timeout=5)
        else:
            raise ValueError(f"Unsupported method: {method}")
            
        return response.json() if response.content else {}
        
    except requests.exceptions.RequestException:
        # Fallback to localhost (development mode)
        try:
            url = f"{CONTROLLER_API_LOCAL}/{endpoint}"
            
            if method == 'GET':
                response = requests.get(url, timeout=5)
            elif method == 'POST':
                response = requests.post(url, json=data, timeout=5)
            elif method == 'DELETE':
                response = requests.delete(url, timeout=5)
            
            return response.json() if response.content else {}
            
        except Exception as e:
            logger.error(f"Controller API call failed: {e}")
            return {'error': 'Controller service unavailable'}

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/control')
def control():
    """Device control page"""
    return render_template('control.html')

@app.route('/analytics')
def analytics():
    """Analytics page route"""
    return render_template('analytics.html')

@app.route('/optimizer')
def optimizer():
    """ML Optimizer information page route"""
    return render_template('optimizer.html')

# API Routes

# API Proxy Endpoints - Forward requests to controller

@app.route('/api/status')
def api_status():
    """WebApp health check with dashboard-compatible data"""
    controller_status = call_controller_api('status')
    devices_data = call_controller_api('devices')
    
    # Count online nodes
    nodes_online = len(devices_data) if isinstance(devices_data, dict) else 0
    
    # Transform controller status to match frontend expectations
    dashboard_status = {
        'webapp_status': 'running',
        'controller_status': controller_status,
        'system_status': {
            'mqtt_connected': controller_status.get('status') == 'running',
            'db_connected': controller_status.get('status') == 'running',
            'nodes_online': nodes_online
        },
        'energy_stats': {
            'total_consumption': sum(
                device.get('latest_data', {}).get('room_usage', 0) 
                for device in devices_data.values()
            ) if isinstance(devices_data, dict) else 0,
            'energy_saved': controller_status.get('energy_stats', {}).get('energy_saved', 0),
            'optimization_events': controller_status.get('energy_stats', {}).get('ml_optimizations', 0),
            'manual_overrides': controller_status.get('active_overrides', 0)
        },
        'latest_data': {
            device_id: {
                'data': device_data.get('latest_data', {}),
                'timestamp': device_data.get('latest_data', {}).get('timestamp', ''),
                'type': 'sensor'
            }
            for device_id, device_data in devices_data.items()
        } if isinstance(devices_data, dict) else {},
        'timestamp': datetime.now().isoformat()
    }
    
    return jsonify(dashboard_status)

@app.route('/api/devices')
def api_devices():
    """Get device status from controller"""
    return jsonify(call_controller_api('devices'))

@app.route('/api/sensor-data')
def api_sensor_data():
    """Get recent sensor data from controller"""
    return jsonify(call_controller_api('sensor-data'))

@app.route('/api/historical/<int:hours>')
def api_historical_data(hours):
    """Get historical sensor data for the specified number of hours"""
    # For now, simulate historical data based on current sensor readings
    # In a real implementation, this would query the database
    current_data = call_controller_api('sensor-data')
    
    # Generate simulated historical data
    import random
    from datetime import datetime, timedelta
    
    historical_data = []
    if isinstance(current_data, list):
        base_time = datetime.now()
        for i in range(min(hours * 12, 100)):  # 12 points per hour, max 100 points
            timestamp = base_time - timedelta(minutes=i * 5)
            
            for device_id in ['node1', 'node2', 'node3']:
                # Add some variation to current data
                usage_base = 0.1 if device_id == 'node1' else (0.15 if device_id == 'node2' else 0.08)
                room_usage = max(0, usage_base + random.uniform(-0.05, 0.05))
                
                historical_data.append({
                    'device_id': device_id,
                    'timestamp': timestamp.isoformat(),
                    'data': {
                        'room_usage': room_usage,
                        'lux': random.randint(20, 80),
                        'occupancy': random.choice([0, 1]),
                        'temperature': random.uniform(20, 25),
                        'led_status': random.choice([0, 1]),
                        'energy_saving_mode': random.choice([0, 1]),
                        'manual_override': random.choice([0, 0, 0, 1])  # 25% chance
                    }
                })
    
    return jsonify({'data': historical_data})

@app.route('/api/devices/<device_id>/override', methods=['POST'])
def api_set_override(device_id):
    """Set device override via controller"""
    data = request.get_json()
    result = call_controller_api(f'devices/{device_id}/override', 'POST', data)
    
    # Emit real-time update
    socketio.emit('device_update', {
        'device_id': device_id,
        'override': data,
        'timestamp': datetime.now().isoformat()
    })
    
    return jsonify(result)

@app.route('/api/devices/<device_id>/override', methods=['DELETE'])
def api_remove_override(device_id):
    """Remove device override via controller"""
    result = call_controller_api(f'devices/{device_id}/override', 'DELETE')
    
    # Emit real-time update
    socketio.emit('device_update', {
        'device_id': device_id,
        'override_removed': True,
        'timestamp': datetime.now().isoformat()
    })
    
    return jsonify(result)

@app.route('/api/system/refresh', methods=['POST'])
def refresh_system():
    """Refresh system via controller API"""
    result = call_controller_api('system/refresh', 'POST')
    return jsonify(result)

@app.route('/api/devices/all/control', methods=['POST'])
def global_device_control():
    """Global device control via controller API"""
    data = request.get_json()
    result = call_controller_api('devices/all/control', 'POST', data)
    return jsonify(result)

@app.route('/api/devices/all/override/clear', methods=['POST'])
def clear_all_overrides():
    """Clear all device overrides via controller API"""
    result = call_controller_api('devices/all/override/clear', 'POST')
    return jsonify(result)

@app.route('/api/model-info')
def get_model_info():
    """Get ML model information via controller API"""
    return jsonify(call_controller_api('model-info'))

# WebSocket Events for Real-time Updates

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info('Client connected')
    emit('connected', {'message': 'Connected to IoT Energy Management System'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info('Client disconnected')

@socketio.on('request_device_status')
def handle_device_status_request():
    """Send current device status to client"""
    devices = call_controller_api('devices')
    emit('device_status', devices)

@socketio.on('request_sensor_data')
def handle_sensor_data_request():
    """Send current sensor data to client"""
    sensor_data = call_controller_api('sensor-data')
    emit('sensor_data', sensor_data)

@socketio.on('request_control')
def handle_control_request(data):
    """Handle device control requests"""
    device_id = data.get('device_id')
    command = data.get('command')
    
    if not device_id or not command:
        emit('control_response', {
            'success': False,
            'device_id': device_id,
            'command': command,
            'error': 'Missing device_id or command'
        })
        return
    
    # Map command to override API call
    override_data = {
        'status': 'on' if command == 'on' else 'off',
        'type': '24h'  # Default to 24h override
    }
    
    result = call_controller_api(f'devices/{device_id}/override', 'POST', override_data)
    
    emit('control_response', {
        'success': not result.get('error'),
        'device_id': device_id,
        'command': command,
        'result': result
    })
    
    # Broadcast the control event to all clients
    socketio.emit('device_update', {
        'device_id': device_id,
        'command': command,
        'timestamp': datetime.now().isoformat()
    })

# Background Tasks

def realtime_updates():
    """Background thread for real-time data updates"""
    while True:
        try:
            # Get fresh data from controller
            devices = call_controller_api('devices')
            sensor_data = call_controller_api('sensor-data')
            
            # Broadcast to all connected clients
            socketio.emit('device_status_update', devices)
            socketio.emit('sensor_data_update', sensor_data)
            
        except Exception as e:
            logger.error(f"Real-time update error: {e}")
        
        time.sleep(1)  # Update every 1 second

# Error Handlers

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Page not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# Template Filters

@app.template_filter('datetime_format')
def datetime_format(value):
    """Format datetime for templates"""
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            return value
    return value

if __name__ == '__main__':
    # Start background thread for real-time updates
    thread = threading.Thread(target=realtime_updates, daemon=True)
    thread.start()
    
    logger.info("🌐 Starting IoT Energy Management WebApp...")
    logger.info("📊 Dashboard: http://localhost:5000")
    logger.info("🎛️ Control: http://localhost:5000/control")
    logger.info("📈 Analytics: http://localhost:5000/analytics")
    
    # Run the Flask-SocketIO app
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
