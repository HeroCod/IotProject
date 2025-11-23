/**
 * Control Page - Device Controls
 */

import { addLogEntry, devices } from './config.js';

export function getDurationValue(sliderValue) {
    const val = parseInt(sliderValue);
    if (val === 0) return 'permanent';
    if (val === 1) return '1h';
    if (val === 4) return '4h';
    if (val === 12) return '12h';
    if (val === 24) return '24h';
    return '24h';
}

export function saveDuration(deviceId, value) {
    localStorage.setItem(`duration-${deviceId}`, value);
}

export function sendCommand(deviceId, command) {
    const durationSelect = document.getElementById(`duration-${deviceId}`);
    const duration = getDurationValue(durationSelect ? durationSelect.value : '24');

    const overrideData = {
        status: command,
        type: duration
    };

    fetch(`/api/devices/${deviceId}/override`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(overrideData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            addLogEntry(deviceId, `Override set: LED ${command.toUpperCase()} for ${duration}`);
            showResponse(deviceId, `LED ${command.toUpperCase()} override set for ${duration}`, 'success');
            setTimeout(() => window.refreshDevices && window.refreshDevices(), 1000);
        } else {
            addLogEntry(deviceId, `Override failed: ${data.error || 'Unknown error'}`);
            showResponse(deviceId, `Override failed: ${data.error || 'Unknown error'}`, 'error');
        }
    })
    .catch(error => {
        addLogEntry(deviceId, `Override error: ${error.message}`);
        showResponse(deviceId, `Override error: ${error.message}`, 'error');
    });
}

export function removeOverride(deviceId) {
    fetch(`/api/devices/${deviceId}/override`, {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            addLogEntry(deviceId, 'Returned to AUTO mode');
            showResponse(deviceId, 'Returned to AUTO mode', 'success');
            setTimeout(() => window.refreshDevices && window.refreshDevices(), 1000);
        } else {
            addLogEntry(deviceId, `Auto mode failed: ${data.error || 'Unknown error'}`);
            showResponse(deviceId, `Auto mode failed: ${data.error || 'Unknown error'}`, 'error');
        }
    })
    .catch(error => {
        addLogEntry(deviceId, `Auto mode error: ${error.message}`);
        showResponse(deviceId, `Auto mode error: ${error.message}`, 'error');
    });
}

export function globalCommand(target, command) {
    Object.keys(devices).forEach(deviceId => {
        sendCommand(deviceId, command);
    });

    showGlobalResponse(`Sending ${command.toUpperCase()} command to all devices`, 'success');
}

export function enableEnergyMode() {
    showGlobalResponse('Energy saving mode is automatically managed by the ML system', 'info');
}

export function showResponse(deviceId, message, type) {
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

export function showGlobalResponse(message, type) {
    const responseDiv = document.getElementById('global-response');
    if (responseDiv) {
        responseDiv.className = `response-message message-${type}`;
        responseDiv.textContent = message;
        responseDiv.style.display = 'block';

        setTimeout(() => {
            responseDiv.style.display = 'none';
        }, 3000);
    }
}
