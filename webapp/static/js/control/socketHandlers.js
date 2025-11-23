/**
 * Socket Handlers Module
 *
 * Manages Socket.IO event handlers for real-time updates.
 */

import { updateDevice } from './deviceCards.js';
import { refreshDevices } from './deviceCards.js';
import { addLogEntry } from './config.js';

/**
 * Show response message for a specific device
 */
function showResponse(deviceId, message, type) {
    const responseDiv = document.getElementById(`response-${deviceId}`);
    if (responseDiv) {
        responseDiv.className = `response-message message-${type}`;
        responseDiv.textContent = message;
        responseDiv.style.display = 'block';

        setTimeout(() => {
            responseDiv.style.display = 'none';
        }, 3000);
    }
}

/**
 * Initialize Socket.IO event handlers
 */
export function initializeSocketHandlers(socket) {
    socket.on('connect', function() {
        console.log('Connected to server');
        refreshDevices();
    });

    socket.on('system_status', function(data) {
        Object.entries(data.latest_data || {}).forEach(([deviceId, deviceData]) => {
            updateDevice(deviceId, deviceData.data, deviceData.timestamp);
        });
    });

    socket.on('sensor_update', function(data) {
        updateDevice(data.device_id, data.data, data.timestamp);
    });

    socket.on('control_response', function(data) {
        const status = data.success ? 'success' : 'error';
        const message = data.success
            ? `✅ ${data.command.toUpperCase()} command successful`
            : `❌ Failed to send ${data.command} command`;

        showResponse(data.device_id, message, status);
        addLogEntry(data.device_id, message);
    });
}
