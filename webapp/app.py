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
import time
from datetime import datetime
import logging

import asyncio
from aiocoap import Message, Context
from aiocoap.numbers import PUT

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'iot_webapp_secret_key_2024'
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

# Controller API configuration
CONTROLLER_API_BASE = 'http://localhost:5001/api'  # Use localhost since all services use network_mode: host
CONTROLLER_API_LOCAL = 'http://localhost:5001/api'  # Same as base for host networking

async def send_coap_request(uri, payload):
    request = Message(code=PUT, payload=payload.encode('utf-8'))
    request.set_request_uri(uri)
    protocol = await Context.create_client_context(transports=['udp6'])
    try:
        response = await protocol.request(request).response
        print(f"CoAP Response: {response.code}")
        return response.payload.decode('utf-8')
    except Exception as e:
        print(f"CoAP Error: {e}")
        return None
    finally:
        await protocol.shutdown()



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

@app.route('/scheduler')
def scheduler():
    """Temperature schedule manager page"""
    return render_template('scheduler.html')

@app.route('/optimizer')
def optimizer():
    """ML Optimizer information page route"""
    return render_template('optimizer.html')

@app.route('/health', methods=['GET'])
def health_check():
    """Webapp health check endpoint"""
    try:
        # Test controller connectivity
        controller_status = call_controller_api('health')
        controller_ok = not (isinstance(controller_status, dict) and controller_status.get('error'))

        health_status = {
            'status': 'healthy' if controller_ok else 'degraded',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'webapp': 'running',
                'controller': 'connected' if controller_ok else 'disconnected',
                'socketio': 'running'
            },
            'controller_status': controller_status if controller_ok else {'error': 'unavailable'}
        }

        return jsonify(health_status)
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/status')
def api_status():
    """WebApp health check with dashboard-compatible data"""
    print("=== DEBUG: WebApp /api/status called ===")
    controller_status = call_controller_api('status')
    devices_data = call_controller_api('devices')

    # Debug logging
    print(f"Controller status: {controller_status}")
    print(f"Controller energy_stats: {controller_status.get('energy_stats', 'NOT FOUND')}")
    logger.info(f"Controller status: {controller_status}")
    logger.info(f"Controller energy_stats: {controller_status.get('energy_stats', 'NOT FOUND')}")

    # Count online nodes
    nodes_online = len(devices_data) if isinstance(devices_data, dict) else 0

    # Calculate optimizer active status: active unless all nodes have overrides
    nodes_with_override = sum(1 for device in devices_data.values() if isinstance(device, dict) and device.get('override', {}).get('active', False))
    optimizer_active = nodes_online > 0 and nodes_with_override < nodes_online

    # Transform controller status to match frontend expectations
    controller_energy_stats = controller_status.get('energy_stats', {}) if isinstance(controller_status, dict) else {}

    # Calculate current consumption (sum of all current room_usage, kWh)
    current_total_consumption = sum(
        (device.get('latest_data') or {}).get('room_usage_wh', 0) / 1000.0
        for device in devices_data.values() if isinstance(device, dict)
    ) if isinstance(devices_data, dict) else 0

    # Calculate estimated total consumption from accumulated stats
    estimated_total_consumption = 0
    if isinstance(controller_energy_stats, dict):
        # Estimate baseline consumption: assume each decision could have used 0.15kWh if lights were always on
        total_decisions = controller_energy_stats.get('total_decisions', 0)
        energy_saved = controller_energy_stats.get('energy_saved', 0)

        # Estimated baseline if lights were always on when occupied (simplified calculation)
        estimated_baseline = total_decisions * 0.05  # Average 0.05kWh per decision (conservative estimate)
        estimated_total_consumption = estimated_baseline - energy_saved

    dashboard_status = {
        'webapp_status': 'running',
        'controller_status': controller_status,
        'system_status': {
            'mqtt_connected': controller_status.get('status') == 'running' if isinstance(controller_status, dict) else False,
            'db_connected': controller_status.get('status') == 'running' if isinstance(controller_status, dict) else False,
            'nodes_online': nodes_online
        },
        'energy_stats': {
            # Use estimated total consumption if significant, otherwise current snapshot
            'total_consumption': max(estimated_total_consumption, current_total_consumption),
            'energy_saved': controller_energy_stats.get('energy_saved', 0) if isinstance(controller_energy_stats, dict) else 0,
            'optimization_events': controller_energy_stats.get('optimization_events', 0) if isinstance(controller_energy_stats, dict) else 0,
            'manual_overrides': controller_status.get('active_overrides', 0) if isinstance(controller_status, dict) else 0
        },
        'optimizer_active': optimizer_active,
        'latest_data': {
            device_id: {
                'data': {
                    **(device_data.get('latest_data') or {}),
                    'room_usage': (device_data.get('latest_data') or {}).get('room_usage_wh', 0) / 1000.0,
                    'room_usage_wh': (device_data.get('latest_data') or {}).get('room_usage_wh', 0),  # Keep Wh for charts
                    'predicted_temp': (device_data.get('latest_data') or {}).get('predicted_temp', 0),
                    'target_temp': (device_data.get('latest_data') or {}).get('target_temp', 0),
                    'heating_status': (device_data.get('latest_data') or {}).get('heating_status', 0)
                },
                'timestamp': (device_data.get('latest_data') or {}).get('timestamp', ''),
                'type': 'sensor'
            }
            for device_id, device_data in devices_data.items()
            if isinstance(device_data, dict)
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
    # Get real historical data from the controller
    controller_data = call_controller_api(f'sensor-data?hours={hours}')

    # Transform controller data format to match analytics expectations
    historical_data = []

    if isinstance(controller_data, list):
        # Limit the data to prevent overwhelming the frontend (max 500 points)
        limited_data = controller_data[:min(len(controller_data), 500)]

        for item in limited_data:
            device_id = item.get('device_id')
            payload = item.get('payload', {})
            timestamp = item.get('timestamp')

            # Transform to match expected format - keep ALL fields from payload
            transformed_item = {
                'device_id': device_id,
                'timestamp': payload.get('timestamp', timestamp),  # Use payload timestamp if available
                'data': {
                    # Keep original field names and units for consistency with frontend
                    'room_usage_wh': payload.get('room_usage_wh', 0),
                    'room_usage': payload.get('room_usage_wh', 0) / 1000.0,  # Also provide kWh version
                    'occupancy': payload.get('occupancy', 0),
                    'sim_occupancy': payload.get('sim_occupancy'),  # Include simulated occupancy (ground truth)
                    'temperature': payload.get('temperature'),
                    'lux': payload.get('lux'),  # Keep original field name
                    'light_level': payload.get('lux'),  # Also provide alias
                    'humidity': payload.get('humidity'),
                    'co2': payload.get('co2'),
                    'led_status': payload.get('led_status', 0),
                    'manual_override': payload.get('manual_override', False),
                    'optimization_event': payload.get('optimization_event', 0),
                    'location': payload.get('location', device_id)
                }
            }
            historical_data.append(transformed_item)

    # If no data available, return empty result
    if not historical_data:
        print(f"⚠️ No historical data available for {hours} hours from controller")
        return jsonify({'data': []})

    print(f"📊 Returning {len(historical_data)} historical data points for {hours} hours")
    return jsonify({'data': historical_data})

@app.route('/api/devices/<device_id>/override', methods=['POST'])
def api_set_override(device_id):
    """Set device override via controller"""
    data = request.get_json()
    result = call_controller_api(f'devices/{device_id}/override', 'POST', data)

    # Emit targeted override update instead of general device_update
    # This prevents full page refreshes while still updating relevant UI elements
    socketio.emit('override_update', {
        'device_id': device_id,
        'override': data,
        'timestamp': datetime.now().isoformat(),
        'action': 'set'
    })

    return jsonify(result)

@app.route('/api/devices/<device_id>/override', methods=['DELETE'])
def api_remove_override(device_id):
    """Remove device override via controller"""
    result = call_controller_api(f'devices/{device_id}/override', 'DELETE')

    # Emit targeted override update instead of general device_update
    # This prevents full page refreshes while still updating relevant UI elements
    socketio.emit('override_update', {
        'device_id': device_id,
        'override_removed': True,
        'timestamp': datetime.now().isoformat(),
        'action': 'remove'
    })

    return jsonify(result)

@app.route('/api/devices/<device_id>/led', methods=['POST'])
def api_set_led_control(device_id):
    """Set LED control via controller"""
    data = request.get_json()
    result = call_controller_api(f'devices/{device_id}/led', 'POST', data)

    # Emit control update
    socketio.emit('control_update', {
        'device_id': device_id,
        'control_type': 'led',
        'status': data.get('status'),
        'timestamp': datetime.now().isoformat()
    })

    return jsonify(result)

@app.route('/api/devices/<device_id>/heating', methods=['POST'])
def api_set_heating_control(device_id):
    """Set heating control via controller"""
    data = request.get_json()
    result = call_controller_api(f'devices/{device_id}/heating', 'POST', data)

    # Emit control update
    socketio.emit('control_update', {
        'device_id': device_id,
        'control_type': 'heating',
        'status': data.get('status'),
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

@app.route('/api/devices/all/led', methods=['POST'])
def global_led_control():
    """Global LED control via controller API"""
    data = request.get_json()
    result = call_controller_api('devices/all/led', 'POST', data)
    return jsonify(result)

@app.route('/api/devices/all/led/auto', methods=['POST'])
def global_led_auto():
    """Set all LEDs to auto mode via controller API"""
    result = call_controller_api('devices/all/led/auto', 'POST')
    return jsonify(result)

@app.route('/api/devices/all/heating', methods=['POST'])
def global_heating_control():
    """Global heating control via controller API"""
    data = request.get_json()
    result = call_controller_api('devices/all/heating', 'POST', data)
    return jsonify(result)

@app.route('/api/devices/all/heating/auto', methods=['POST'])
def global_heating_auto():
    """Set all heating to auto mode via controller API"""
    result = call_controller_api('devices/all/heating/auto', 'POST')
    return jsonify(result)

@app.route('/api/historical/clear', methods=['POST'])
def clear_historical_data():
    """Clear all historical sensor data from the database"""
    try:
        result = call_controller_api('historical/clear', 'POST')
        print(f"🗑️ Historical data cleared: {result}")
        return jsonify(result)
    except Exception as e:
        print(f"❌ Error clearing historical data: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/clock_sync', methods=['POST'])
def force_clock_sync():
    """Force clock synchronization for all devices via controller API"""
    try:
        result = call_controller_api('clock_sync', 'POST')
        print(f"🕐 Clock sync triggered: {result}")
        return jsonify(result)
    except Exception as e:
        print(f"❌ Error forcing clock sync: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/schedule/<device_id>', methods=['GET'])
def get_schedule(device_id):
    """Get temperature schedule for device via controller API"""
    result = call_controller_api(f'schedule/{device_id}', 'GET')
    return jsonify(result)

@app.route('/api/schedule/<device_id>', methods=['POST'])
def update_schedule(device_id):
    """Update temperature schedule for device via controller API"""
    data = request.get_json()
    result = call_controller_api(f'schedule/{device_id}', 'POST', data)

    # Emit schedule update event
    socketio.emit('schedule_update', {
        'device_id': device_id,
        'timestamp': datetime.now().isoformat()
    })

    return jsonify(result)

@app.route('/api/heating/<device_id>/control', methods=['POST'])
def control_heating(device_id):
    """Control heating for device via controller API"""
    data = request.get_json()
    result = call_controller_api(f'heating/{device_id}/control', 'POST', data)

    # Emit heating control update
    socketio.emit('heating_update', {
        'device_id': device_id,
        'command': data.get('command'),
        'timestamp': datetime.now().isoformat()
    })

    return jsonify(result)

@app.route('/api/presets/schedule/<preset_name>', methods=['GET'])
def get_preset_schedule(preset_name):
    """Get a preset temperature schedule"""
    presets = {
        'comfort': {
            'name': 'Comfort Schedule',
            'description': '22°C during day (6am-10pm), 18°C at night',
            'schedule': [18]*6 + [22]*16 + [18]*2  # Repeat for 7 days
        },
        'eco': {
            'name': 'Eco Schedule',
            'description': '20°C during day (7am-11pm), 16°C at night',
            'schedule': [16]*7 + [20]*16 + [16]*1
        },
        'work': {
            'name': 'Work From Home',
            'description': '22°C working hours (8am-6pm), 18°C otherwise',
            'schedule': [18]*8 + [22]*10 + [18]*6
        },
        'away': {
            'name': 'Away/Vacation',
            'description': '15°C constant (frost protection)',
            'schedule': [15]*24  # 15°C all day
        }
    }

    if preset_name not in presets:
        return jsonify({'success': False, 'error': 'Unknown preset'}), 404

    preset = presets[preset_name]
    # Expand single day to full week (168 hours)
    full_schedule = preset['schedule'] * 7

    return jsonify({
        'success': True,
        'preset': preset_name,
        'name': preset['name'],
        'description': preset['description'],
        'schedule': full_schedule
    })

@app.route('/api/device-locations')
def api_device_locations():
    """Get device locations from controller"""
    return jsonify(call_controller_api('device-locations'))

@app.route('/api/schedules', methods=['GET'])
def get_all_schedules():
    """Get all saved schedules"""
    result = call_controller_api('schedules', 'GET')
    return jsonify(result)

@app.route('/api/schedules/<int:schedule_id>', methods=['GET'])
def get_schedule_by_id(schedule_id):
    """Get specific schedule by ID"""
    result = call_controller_api(f'schedules/{schedule_id}', 'GET')
    return jsonify(result)

@app.route('/api/schedules', methods=['POST'])
def create_schedule():
    """Create new schedule"""
    data = request.get_json()
    result = call_controller_api('schedules', 'POST', data)
    return jsonify(result)

@app.route('/api/schedules/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    """Delete schedule"""
    result = call_controller_api(f'schedules/{schedule_id}', 'DELETE')
    return jsonify(result)

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

    # Fetch device data to get URI dynamically
    devices = call_controller_api('devices')
    uri = None
    if isinstance(devices, dict) and device_id in devices:
        device_info = devices[device_id]
        if isinstance(device_info, dict):
            uri = device_info.get('uri')

    if not uri:
        emit('control_response', {
            'success': False,
            'device_id': device_id,
            'command': command,
            'error': 'Unknown device or missing URI'
        })
        return

    if command == 'on':
        payload = '{"mo": 1, "ls": 1}'
    elif command == 'off':
        payload = '{"mo": 1, "ls": 0}'
    else:
        emit('control_response', {
            'success': False,
            'device_id': device_id,
            'command': command,
            'error': 'Invalid command'
        })
        return

    result = asyncio.run(send_coap_request(uri, payload))

    emit('control_response', {
        'success': result is not None,
        'device_id': device_id,
        'command': command,
        'result': result
    })

    # Emit targeted graph update event instead of general device_update
    # This prevents full page refreshes while still updating graphs
    socketio.emit('graph_control_update', {
        'device_id': device_id,
        'command': command,
        'timestamp': datetime.now().isoformat(),
        'type': 'control_action',  # Specify this is from a control action
        'led_status': command  # Include the new LED status for graph updates
    })

# Background Tasks

# Global variable to store the last emitted graph data
last_emitted_graph_data = None

def realtime_updates():
    """Background thread for real-time graph data updates only - prevents UI interference"""
    global last_emitted_graph_data
    logger.info("📊 Starting graph-only real-time updates (1-second intervals)")
    while True:
        try:
            # Get only the minimal data needed for graphs to prevent UI interference
            sensor_data = call_controller_api('sensor-data?hours=1')  # Last hour only for graphs
            energy_stats = call_controller_api('energy-stats')
            devices_status = call_controller_api('devices')  # For current LED status in graphs

            print(f"DEBUG: sensor_data type: {type(sensor_data)}, length: {len(sensor_data) if isinstance(sensor_data, list) else 'N/A'}")
            if isinstance(sensor_data, list) and sensor_data:
                print(f"DEBUG: first sensor item: {sensor_data[0]}")

            # Calculate optimizer active status: active unless all nodes have overrides
            nodes_with_override = sum(1 for device in devices_status.values() if isinstance(device, dict) and device.get('override', {}).get('active', False))
            total_nodes = len([d for d in devices_status.values() if isinstance(d, dict)])
            optimizer_active = total_nodes > 0 and nodes_with_override < total_nodes

            # Extract latest sensor data for each device from the sensor_data list
            latest_sensor_data = {}
            if isinstance(sensor_data, list):
                # Sort by timestamp descending to get latest first - ensure all timestamps are strings
                for item in sensor_data:
                    timestamp = item.get('timestamp', '')
                    if isinstance(timestamp, datetime):
                        timestamp = timestamp.isoformat()
                    elif not isinstance(timestamp, str):
                        timestamp = str(timestamp)
                    item['timestamp'] = timestamp

                sorted_data = sorted(sensor_data, key=lambda x: x.get('timestamp', ''), reverse=True)
                for item in sorted_data:
                    device_id = item.get('device_id')
                    if device_id and device_id not in latest_sensor_data:
                        payload = item.get('payload', {})
                        latest_sensor_data[device_id] = {
                            'room_usage_wh': payload.get('room_usage_wh', 0),  # Keep in Wh for charts
                            'room_usage': payload.get('room_usage_wh', 0) / 1000.0,  # Also provide kWh
                            'temperature': payload.get('temperature', 22),
                            'predicted_temp': payload.get('predicted_temp', 0),  # Add predicted temp
                            'target_temp': payload.get('target_temp', 0),  # Add target temp
                            'heating_status': payload.get('heating_status', 0),  # Add heating status
                            'lux': payload.get('lux', 50),
                            'occupancy': payload.get('occupancy', 0),
                            'humidity': payload.get('humidity', 30),
                            'co2': payload.get('co2', 400),
                            'location': payload.get('location', device_id),
                            'sim_occupancy': payload.get('sim_occupancy', 0),
                            'timestamp': payload.get('timestamp', item.get('timestamp', ''))
                        }

            print(f"DEBUG: latest_sensor_data: {latest_sensor_data}")

            # Extract only graph-relevant data to minimize payload and prevent UI interference
            graph_data = {
                'timestamp': datetime.now().isoformat(),
                'sensor_points': len(sensor_data) if isinstance(sensor_data, list) else 0,
                'energy_stats': {
                    'total_consumption': energy_stats.get('total_consumption', 0) if isinstance(energy_stats, dict) else 0,
                    'energy_saved': energy_stats.get('energy_saved', 0) if isinstance(energy_stats, dict) else 0,
                    'optimization_events': energy_stats.get('optimization_events', 0) if isinstance(energy_stats, dict) else 0
                },
                'optimizer_active': optimizer_active,
                'current_devices': {
                    device_id: {
                        'led_status': device_data.get('override', {}).get('status', 'auto') if isinstance(device_data, dict) else 'auto',
                        'has_override': device_data.get('override', {}).get('active', False) if isinstance(device_data, dict) else False,
                        'latest_sensor': latest_sensor_data.get(device_id, device_data.get('latest_data', {}) if isinstance(device_data, dict) else {})
                    }
                    for device_id, device_data in devices_status.items() if isinstance(devices_status, dict)
                } if isinstance(devices_status, dict) else {}
            }

            print(f"DEBUG: graph_data current_devices: {list(graph_data['current_devices'].keys())}")

            # Check if the data has changed before emitting
            current_data_json = json.dumps(graph_data, sort_keys=True)
            if last_emitted_graph_data != current_data_json:
                # Emit graph-only update with minimal data to prevent button/control interference
                socketio.emit('graph_only_update', graph_data)
                last_emitted_graph_data = current_data_json
                logger.debug(f"📊 Emitted graph-only update with {graph_data['sensor_points']} sensor points")
                print(f"DEBUG: Emitted graph_only_update")
            else:
                logger.debug("📊 No changes in graph data, skipping emit")
                print(f"DEBUG: No changes, skipping emit")

            # Emit sensor updates for each device to update the cards
            for device_id, sensor_data in latest_sensor_data.items():
                socketio.emit('sensor_update', {
                    'device_id': device_id,
                    'data': sensor_data,
                    'timestamp': sensor_data.get('timestamp', datetime.now().isoformat()),
                    'type': 'sensor'
                })

            # Emit system status update periodically (every 10 seconds or so)
            # For simplicity, emit on every update for now
            system_status = {
                'latest_data': latest_sensor_data,
                'energy_stats': energy_stats if isinstance(energy_stats, dict) else {},
                'optimizer_active': optimizer_active,
                'timestamp': datetime.now().isoformat()
            }
            socketio.emit('system_status', system_status)

        except Exception as e:
            logger.error(f"Graph real-time update error: {e}")
            print(f"DEBUG: Exception in realtime_updates: {e}")

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
    logger.info("🌐 Starting IoT Energy Management WebApp...")
    logger.info("📊 Dashboard: http://localhost:5000")
    logger.info("🎛️ Control: http://localhost:5000/control")
    logger.info("📈 Analytics: http://localhost:5000/analytics")
    logger.info("🔄 Graph updates: Every 1 second (graph-only to prevent UI interference)")

    # Start background task for real-time updates using SocketIO's background task
    socketio.start_background_task(realtime_updates)

    # Run the Flask-SocketIO app
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
