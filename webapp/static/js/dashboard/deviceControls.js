/**
 * Device Controls
 *
 * Functions for controlling individual devices - LED commands, overrides, and duration management.
 */

// Fetch device override status
export async function fetchDeviceOverride(deviceId) {
    try {
        const response = await fetch('/api/devices');
        const devices = await response.json();
        return devices[deviceId]?.override || null;
    } catch (error) {
        console.error('Error fetching device override:', error);
        return null;
    }
}

// Get duration value from slider
export function getDurationValue(sliderValue) {
    const val = parseInt(sliderValue);
    if (val === 0) return 'permanent';
    if (val === 1) return '1h';
    if (val === 4) return '4h';
    if (val === 12) return '12h';
    if (val === 24) return '24h';
    return '24h';
}

// Save duration preference
export function saveDuration(deviceId, value) {
    localStorage.setItem(`duration-${deviceId}`, value);
}

// Send override command
export function sendOverrideCommand(deviceId, command) {
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
            console.log(`✅ Override set: ${deviceId} LED ${command.toUpperCase()} for ${duration}`);
            // Refresh handled by calling module
        } else {
            console.error(`❌ Override failed: ${data.error || 'Unknown error'}`);
        }
    })
    .catch(error => {
        console.error(`❌ Override error: ${error.message}`);
    });
}

// Remove override (return to auto mode)
export function removeOverride(deviceId) {
    fetch(`/api/devices/${deviceId}/override`, {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log(`✅ ${deviceId} returned to AUTO mode`);
            // Refresh handled by calling module
        } else {
            console.error(`❌ Auto mode failed: ${data.error || 'Unknown error'}`);
        }
    })
    .catch(error => {
        console.error(`❌ Auto mode error: ${error.message}`);
    });
}

// Send LED control command to node1 (or other nodes)
export function sendLedCommand(deviceId, command) {
    const durationSelect = document.getElementById(`duration-${deviceId}`);
    const duration = getDurationValue(durationSelect ? durationSelect.value : '24');

    const ledData = {
        control_type: 'led',
        status: command,
        type: duration
    };

    fetch(`/api/devices/${deviceId}/led`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(ledData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log(`✅ LED command sent: ${deviceId} LED ${command.toUpperCase()} for ${duration}`);
        } else {
            console.error(`❌ LED command failed: ${data.error || 'Unknown error'}`);
        }
    })
    .catch(error => {
        console.error(`❌ LED command error: ${error.message}`);
    });
}

// Send heating control command to node1
export function sendHeatingCommand(deviceId, command) {
    const durationSelect = document.getElementById(`duration-${deviceId}`);
    const duration = getDurationValue(durationSelect ? durationSelect.value : '24');

    const heatingData = {
        control_type: 'heating',
        status: command,
        type: duration
    };

    fetch(`/api/devices/${deviceId}/heating`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(heatingData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log(`✅ Heating command sent: ${deviceId} HEATING ${command.toUpperCase()} for ${duration}`);
        } else {
            console.error(`❌ Heating command failed: ${data.error || 'Unknown error'}`);
        }
    })
    .catch(error => {
        console.error(`❌ Heating command error: ${error.message}`);
    });
}

// Send LED control command (via socket)
export function sendCommand(socket, deviceId, command) {
    socket.emit('request_control', {
        device_id: deviceId,
        command: command
    });
}
