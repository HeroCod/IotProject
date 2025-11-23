/**
 * Global Controls and Statistics
 *
 * Functions for system-wide controls, heating statistics, and status updates.
 */

import { energyChart } from './charts.js';

// Update system status indicators
export function updateStatus(status) {
    const mqttStatus = document.getElementById('mqtt-status');
    const dbStatus = document.getElementById('db-status');
    const aiStatus = document.getElementById('ai-status');
    const mqttText = document.getElementById('mqtt-text');
    const dbText = document.getElementById('db-text');
    const aiText = document.getElementById('ai-text');
    const nodesCount = document.getElementById('nodes-count');

    mqttStatus.className = `status-indicator ${status.system_status.mqtt_connected ? 'status-online' : 'status-offline'}`;
    mqttText.textContent = status.system_status.mqtt_connected ? 'Connected' : 'Disconnected';

    dbStatus.className = `status-indicator ${status.system_status.db_connected ? 'status-online' : 'status-offline'}`;
    dbText.textContent = status.system_status.db_connected ? 'Connected' : 'Disconnected';

    // Update heating system status instead of AI optimizer
    const heatingActive = Object.values(status.latest_data || {}).some(device =>
        device.data && device.data.heating_status === 1
    );
    aiStatus.className = `status-indicator ${heatingActive ? 'status-online' : 'status-offline'}`;
    aiText.textContent = heatingActive ? 'Active' : 'Standby';

    nodesCount.textContent = status.system_status.nodes_online || 0;
}

// Update heating statistics - dynamic cards for each node
export function updateHeatingStats(latestData) {
    const container = document.getElementById('heating-stats-cards');
    if (!container) return;

    // Update or create cards for each node
    Object.entries(latestData).forEach(([deviceId, deviceInfo]) => {
        if (!deviceInfo || !deviceInfo.data) return;

        const data = deviceInfo.data;
        const location = data.location || deviceId;
        
        let card = document.getElementById(`heating-stats-${deviceId}`);
        if (!card) {
            card = document.createElement('div');
            card.className = 'card energy-card';
            card.id = `heating-stats-${deviceId}`;
            container.appendChild(card);
        }

        // Extract values with null checks
        const currentTemp = data.temperature;
        const currentTempText = (currentTemp !== undefined && currentTemp !== null)
            ? currentTemp.toFixed(1) + '°C'
            : '--';

        const predictedTemp = data.predicted_temp;
        const predictedTempText = (predictedTemp !== undefined && predictedTemp !== null && predictedTemp > 0)
            ? predictedTemp.toFixed(1) + '°C'
            : '--';

        const targetTemp = data.target_temp;
        const targetTempText = (targetTemp !== undefined && targetTemp !== null && targetTemp > 0)
            ? targetTemp.toFixed(1) + '°C'
            : 'Not Set';

        const heatingStatus = data.heating_status;
        const heatingStatusText = heatingStatus === 1 ? '🔥 ON' : '❄️ OFF';
        const heatingStatusColor = heatingStatus === 1 ? '#ff4444' : '#4444ff';

        card.innerHTML = `
            <h3>🔥 ${location.charAt(0).toUpperCase() + location.slice(1)} - Heating Statistics</h3>
            <div class="energy-stats">
                <div class="stat-item">
                    <div class="stat-value">${currentTempText}</div>
                    <div class="stat-label">Current Temperature (°C)</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${predictedTempText}</div>
                    <div class="stat-label">Predicted Temperature (°C)</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${targetTempText}</div>
                    <div class="stat-label">Target Temperature (°C)</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" style="color: ${heatingStatusColor};">${heatingStatusText}</div>
                    <div class="stat-label">Heating Status</div>
                </div>
            </div>
        `;
    });
}

// Global command functions
export function globalCommand(target, command) {
    const endpoint = target === 'all' ? 'devices/all/control' : `devices/${target}/control`;

    fetch(`/api/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: `all_${command}` })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showGlobalResponse(`✅ ${command.toUpperCase()} command sent to all devices`, 'success');
        } else {
            showGlobalResponse(`❌ Failed: ${data.error || 'Unknown error'}`, 'error');
        }
    })
    .catch(error => {
        showGlobalResponse(`❌ Error: ${error.message}`, 'error');
    });
}

// Global light control (all devices)
export function globalLightCommand(command) {
    if (command === 'auto') {
        // Clear all overrides to return to auto mode
        fetch('/api/devices/all/led/auto', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showGlobalResponse(`✅ All lights set to AUTO mode`, 'success');
            } else {
                showGlobalResponse(`❌ Failed: ${data.error || 'Unknown error'}`, 'error');
            }
        })
        .catch(error => {
            showGlobalResponse(`❌ Error: ${error.message}`, 'error');
        });
    } else {
        // Send LED command to all devices
        fetch('/api/devices/all/led', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: command, type: '24h' })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const count = data.devices?.length || 0;
                showGlobalResponse(`✅ All lights turned ${command.toUpperCase()} (${count} devices)`, 'success');
            } else {
                showGlobalResponse(`❌ Failed: ${data.error || 'Unknown error'}`, 'error');
            }
        })
        .catch(error => {
            showGlobalResponse(`❌ Error: ${error.message}`, 'error');
        });
    }
}

// Global heating control (all devices)
export function globalHeatingCommand(command) {
    if (command === 'auto') {
        // Clear all heating overrides to return to auto mode
        fetch('/api/devices/all/heating/auto', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showGlobalResponse(`✅ All heating systems set to AUTO mode`, 'success');
            } else {
                showGlobalResponse(`❌ Failed: ${data.error || 'Unknown error'}`, 'error');
            }
        })
        .catch(error => {
            showGlobalResponse(`❌ Error: ${error.message}`, 'error');
        });
    } else {
        // Send heating command to all devices
        fetch('/api/devices/all/heating', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: command, type: '24h' })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const count = data.devices?.length || 0;
                showGlobalResponse(`✅ All heating turned ${command.toUpperCase()} (${count} devices)`, 'success');
            } else {
                showGlobalResponse(`❌ Failed: ${data.error || 'Unknown error'}`, 'error');
            }
        })
        .catch(error => {
            showGlobalResponse(`❌ Error: ${error.message}`, 'error');
        });
    }
}

export function refreshSystem() {
    fetch('/api/system/refresh', { method: 'POST' })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showGlobalResponse('🔄 System refreshed successfully', 'success');
        } else {
            showGlobalResponse(`❌ Refresh failed: ${data.error || 'Unknown error'}`, 'error');
        }
    })
    .catch(error => {
        showGlobalResponse(`❌ Refresh error: ${error.message}`, 'error');
    });
}

export function clearAllOverrides() {
    fetch('/api/devices/all/override/clear', { method: 'POST' })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showGlobalResponse(`✅ Auto mode enabled! Cleared overrides for ${data.devices?.length || 0} devices`, 'success');
        } else {
            showGlobalResponse(`❌ Failed: ${data.error || 'Unknown error'}`, 'error');
        }
    })
    .catch(error => {
        showGlobalResponse(`❌ Error: ${error.message}`, 'error');
    });
}

export function setQuickTemp(temperature) {
    showGlobalResponse(`🌡️ Setting quick temperature preset to ${temperature}°C...`, 'info');
    // TODO: Implement quick temperature preset that updates schedule
}

export function loadPresetSchedule(presetName) {
    fetch(`/api/presets/schedule/${presetName}`)
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Apply schedule to node1 (or all nodes)
            return fetch('/api/schedule/node1', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ schedule: data.schedule })
            });
        } else {
            throw new Error(data.error || 'Failed to load preset');
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showGlobalResponse(`✅ ${presetName.toUpperCase()} schedule loaded successfully!`, 'success');
        } else {
            showGlobalResponse(`❌ Failed to apply schedule: ${data.error}`, 'error');
        }
    })
    .catch(error => {
        showGlobalResponse(`❌ Error loading preset: ${error.message}`, 'error');
    });
}

export function uploadSchedule() {
    showGlobalResponse('📤 Schedule upload feature coming soon - upload CSV or JSON schedule files', 'info');
}

export function showSystemStatus() {
    const nodes = document.getElementById('nodes-count').textContent;
    const mqtt = document.getElementById('mqtt-text').textContent;
    const db = document.getElementById('db-text').textContent;
    const heating = document.getElementById('ai-text').textContent;

    showGlobalResponse(
        `📊 System Status: ${nodes} nodes online, MQTT: ${mqtt}, Database: ${db}, Heating: ${heating}`,
        'info'
    );
}

export function clearHistoricalData() {
    if (!confirm('⚠️ WARNING: This will permanently delete ALL historical sensor data and reset all statistics.\n\nThis includes:\n- All sensor readings\n- Energy statistics\n- Temperature history\n- Occupancy data\n\nThis action cannot be undone. Are you sure you want to continue?')) {
        return;
    }

    // Second confirmation
    if (!confirm('🗑️ FINAL CONFIRMATION: Delete all historical data and reset statistics?\n\nClick OK to permanently delete all data.')) {
        return;
    }

    showGlobalResponse('🗑️ Clearing all historical data and resetting statistics...', 'info');

    fetch('/api/historical/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showGlobalResponse(`✅ Successfully cleared ${data.deleted_records || 0} records and reset all statistics`, 'success');
            // Refresh the page after a short delay
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        } else {
            showGlobalResponse(`❌ Failed to clear data: ${data.error || 'Unknown error'}`, 'error');
        }
    })
    .catch(error => {
        showGlobalResponse(`❌ Error clearing data: ${error.message}`, 'error');
    });
}

export function forceClockSync() {
    showGlobalResponse('🕐 Forcing clock synchronization for all devices...', 'info');

    fetch('/api/clock_sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const successCount = data.synced_devices || 0;
            const failedDevices = data.failed_devices || [];
            
            if (failedDevices.length > 0) {
                showGlobalResponse(
                    `⚠️ Clock sync partially successful: ${successCount} devices synced, ${failedDevices.length} failed (${failedDevices.join(', ')})`,
                    'warning'
                );
            } else {
                showGlobalResponse(
                    `✅ Successfully synchronized clocks for ${successCount} device(s)`,
                    'success'
                );
            }
        } else {
            showGlobalResponse(`❌ Clock sync failed: ${data.error || 'Unknown error'}`, 'error');
        }
    })
    .catch(error => {
        showGlobalResponse(`❌ Error during clock sync: ${error.message}`, 'error');
    });
}

export function showGlobalResponse(message, type) {
    const responseEl = document.getElementById('global-response');
    responseEl.textContent = message;
    responseEl.className = `response-message ${type}`;
    responseEl.style.display = 'block';

    setTimeout(() => {
        responseEl.style.display = 'none';
    }, 5000);
}
