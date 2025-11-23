/**
 * WebSocket Event Handlers
 *
 * Socket.IO event handlers for real-time updates.
 */

import { updateStatus, updateHeatingStats } from './globalControls.js';
import { updateSensorCard } from './sensorCards.js';
import { updateChartRealtime } from './charts.js';
import { lastChartUpdate, updateInterval, setLastChartUpdate } from './config.js';

// Initialize Socket.IO connection
export const socket = io();

// Setup all socket event handlers
export function setupSocketHandlers() {
    socket.on('connect', function() {
        console.log('Connected to server');
    });

    socket.on('system_status', function(data) {
        updateStatus(data);
        if (data.latest_data) {
            updateHeatingStats(data.latest_data);
        }

        // Update existing sensor cards
        Object.entries(data.latest_data || {}).forEach(([deviceId, deviceData]) => {
            updateSensorCard(deviceId, deviceData.data, deviceData.timestamp, deviceData.type);
        });
    });

    socket.on('sensor_update', function(data) {
        updateSensorCard(data.device_id, data.data, data.timestamp, data.type);

        // Throttle chart updates based on slider setting
        const now = Date.now();
        if (now - lastChartUpdate >= updateInterval) {
            updateChartRealtime(data.device_id, data.data, data.timestamp);
            setLastChartUpdate(now);
        }
    });

    // Graph-only updates to prevent page movement
    socket.on('graph_only_update', function(data) {
        console.log('📊 Graph-only update received:', data.timestamp);

        // Update AI optimizer status if provided
        if (data.optimizer_active !== undefined) {
            const aiStatus = document.getElementById('ai-status');
            const aiText = document.getElementById('ai-text');
            aiStatus.className = `status-indicator ${data.optimizer_active ? 'status-online' : 'status-warning'}`;
            aiText.textContent = data.optimizer_active ? 'Active' : 'Inactive';
        }

        // Only update charts, no sensor cards

        // Throttle chart updates based on slider setting
        const now = Date.now();
        if (now - lastChartUpdate >= updateInterval) {
            // Update charts with current device data if available
            if (data.current_devices) {
                Object.entries(data.current_devices).forEach(([deviceId, deviceData]) => {
                    if (deviceData.latest_sensor) {
                        console.log('📊 Updating chart for', deviceId, 'with data:', deviceData.latest_sensor);
                        const sensorTimestamp = deviceData.latest_sensor.timestamp || data.timestamp;
                        updateChartRealtime(deviceId, deviceData.latest_sensor, sensorTimestamp);
                    }
                });
            }
            setLastChartUpdate(now);
        }
    });

    socket.on('control_response', function(data) {
        if (data.success) {
            console.log(`✅ Command ${data.command} sent to ${data.device_id}`);
        } else {
            console.log(`❌ Failed to send command to ${data.device_id}`);
        }
    });
}
