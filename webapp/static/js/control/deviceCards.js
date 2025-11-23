/**
 * Device Cards Module
 *
 * Manages device card rendering and updates.
 */

import { devices, activityLogs, addLogEntry } from './config.js';

/**
 * Create HTML for a device card
 */
export function createDeviceCard(deviceId, data) {
    const location = data.latest_data?.location || deviceId;
    const timestamp = data.latest_data?.timestamp || data.timestamp;

    // Debug timestamp parsing
    console.log(`Device ${deviceId} timestamp:`, timestamp);

    let isOnline = false;
    if (timestamp) {
        try {
            // Ensure timestamp is treated as UTC if it doesn't have timezone info
            let timestampToUse = timestamp;
            if (!timestamp.includes('Z') && !timestamp.includes('+') && !timestamp.includes('-', 10)) {
                timestampToUse = timestamp + 'Z'; // Add UTC indicator
            }

            const deviceTime = new Date(timestampToUse).getTime();
            const currentTime = Date.now();
            const timeDiff = currentTime - deviceTime;

            console.log(`Device ${deviceId} original timestamp: ${timestamp}`);
            console.log(`Device ${deviceId} parsed timestamp: ${timestampToUse}`);
            console.log(`Device ${deviceId} device time: ${new Date(deviceTime)}`);
            console.log(`Device ${deviceId} current time: ${new Date(currentTime)}`);
            console.log(`Device ${deviceId} time diff: ${timeDiff}ms (${timeDiff/1000}s)`);

            // More generous timeout - 60 seconds instead of 30
            isOnline = !isNaN(deviceTime) && timeDiff < 60000 && timeDiff >= 0;
            console.log(`Device ${deviceId} isOnline: ${isOnline}`);
        } catch (e) {
            console.error(`Device ${deviceId} timestamp parse error:`, e);
            isOnline = false;
        }
    } else {
        console.log(`Device ${deviceId} has no timestamp`);
    }

    return `
        <div class="device-card" id="device-${deviceId}">
            <div class="device-header">
                <div class="device-title">🏠 ${location.charAt(0).toUpperCase() + location.slice(1)}</div>
                <div class="device-status">
                    <div class="status-dot ${isOnline ? 'status-online' : 'status-offline'}"></div>
                    <span>${isOnline ? 'Online' : 'Offline'}</span>
                </div>
            </div>

            <div class="mode-indicators">
                <div class="mode-indicator ${data.override?.active ? 'mode-manual' : 'mode-auto'}">
                    ${data.override?.active ? '🔧 Manual Mode' : '🤖 Auto Mode'}
                </div>
                ${data.latest_data?.energy_saving_mode ? '<div class="mode-indicator mode-saving">💚 Energy Saving</div>' : ''}
                ${data.latest_data?.led_status ? '<div class="mode-indicator" style="background:#ffebcd;color:#8b4513">💡 LED ON</div>' : ''}
            </div>

            <div class="device-info">
                <div class="info-item">
                    <div class="info-value">${data.latest_data?.lux || 'N/A'}</div>
                    <div class="info-label">💡 Lux</div>
                </div>
                <div class="info-item">
                    <div class="info-value">${data.latest_data?.occupancy ? 'Yes' : 'No'}</div>
                    <div class="info-label">👤 Occupied</div>
                </div>
                <div class="info-item">
                    <div class="info-value">${data.latest_data?.temperature || 'N/A'}°C</div>
                    <div class="info-label">🌡️ Temp</div>
                </div>
                <div class="info-item">
                    <div class="info-value">${(data.latest_data?.room_usage || 0).toFixed(3)}</div>
                    <div class="info-label">⚡ kWh</div>
                </div>
                <div class="info-item">
                    <div class="info-value">${data.latest_data?.button_presses || 0}</div>
                    <div class="info-label">🔘 Button</div>
                </div>
                <div class="info-item">
                    <div class="info-value">${timestamp ? new Date(timestamp).toLocaleTimeString() : 'N/A'}</div>
                    <div class="info-label">🕐 Updated</div>
                </div>
            </div>

            <div class="control-section">
                <div class="section-title">💡 LED Control</div>

                <!-- Override Duration Selection -->
                <div class="duration-selection">
                    <label>Override Duration:</label>
                    <div class="slider-container">
                        <input type="range" id="duration-${deviceId}" class="duration-slider" min="0" max="24" step="1" value="${localStorage.getItem(`duration-${deviceId}`) || '24'}" list="duration-ticks-${deviceId}" onchange="saveDuration('${deviceId}', this.value)" ${!isOnline ? 'disabled' : ''}>
                        <datalist id="duration-ticks-${deviceId}">
                            <option value="0">
                            <option value="1">
                            <option value="4">
                            <option value="12">
                            <option value="24">
                        </datalist>
                        <div class="slider-labels">
                            <span>Permanent</span>
                            <span>1h</span>
                            <span>4h</span>
                            <span>12h</span>
                            <span>24h</span>
                        </div>
                    </div>
                </div>

                <div class="control-buttons">
                    <button class="btn btn-success" onclick="sendCommand('${deviceId}', 'on')" ${!isOnline ? 'disabled' : ''}>
                        💡 LED ON
                    </button>
                    <button class="btn btn-danger" onclick="sendCommand('${deviceId}', 'off')" ${!isOnline ? 'disabled' : ''}>
                        🌙 LED OFF
                    </button>
                    <button class="btn btn-auto" onclick="removeOverride('${deviceId}')" ${!data.override?.active ? 'disabled' : ''}>
                        🤖 AUTO MODE
                    </button>
                </div>

                ${data.override?.active ? `
                    <div class="override-info">
                        <strong>Override Active:</strong> ${data.override.status.toUpperCase()}
                        (${data.override.type}${data.override.expires_at ? ' - expires: ' + new Date(data.override.expires_at).toLocaleString() : ''})
                    </div>
                ` : ''}

                <div class="response-message" id="response-${deviceId}"></div>
            </div>

            <div class="activity-log" id="log-${deviceId}">
                <div class="section-title">📋 Activity Log</div>
                <div id="log-entries-${deviceId}">
                    <!-- Log entries will be added here -->
                </div>
            </div>
        </div>
    `;
}

/**
 * Update device display
 */
export function updateDevice(deviceId, data, timestamp) {
    devices[deviceId] = { data, timestamp };

    const grid = document.getElementById('device-grid');
    const existingCard = document.getElementById(`device-${deviceId}`);

    if (existingCard) {
        existingCard.outerHTML = createDeviceCard(deviceId, data);
    } else {
        grid.innerHTML += createDeviceCard(deviceId, data);
    }

    // Initialize activity log if needed
    if (!activityLogs[deviceId]) {
        activityLogs[deviceId] = [];
    }

    // Add activity log entry
    addLogEntry(deviceId, `Sensor update - Usage: ${(data.room_usage || 0).toFixed(3)} kWh, Mode: ${data.manual_override ? 'Manual' : 'Auto'}`);
}

/**
 * Refresh all devices from API
 */
export function refreshDevices() {
    fetch('/api/devices')
        .then(response => response.json())
        .then(data => {
            console.log('Device data received:', data);
            const container = document.getElementById('device-grid');
            container.innerHTML = '';

            Object.entries(data || {}).forEach(([deviceId, deviceData]) => {
                console.log(`Processing device ${deviceId}:`, deviceData);
                const deviceCard = createDeviceCard(deviceId, deviceData);
                container.innerHTML += deviceCard;
            });
            showGlobalResponse('Device status refreshed', 'success');
        })
        .catch(error => {
            console.error('Device refresh error:', error);
            showGlobalResponse('Failed to refresh device status', 'error');
        });
}

/**
 * Show global response message
 */
function showGlobalResponse(message, type) {
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
