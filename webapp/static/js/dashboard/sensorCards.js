/**
 * Sensor Cards
 *
 * Functions for creating and updating sensor card UI elements.
 */

import { sensorCardCache } from './config.js';
import { fetchDeviceOverride } from './deviceControls.js';

// Create or update sensor card
export function updateSensorCard(deviceId, data, timestamp, type) {
    console.log(`🔧 Checking card for ${deviceId}:`, data);

    // Check if data has actually changed
    const currentData = {
        ...data,
        timestamp: timestamp,
        type: type
    };

    const cachedData = sensorCardCache[deviceId];
    if (cachedData && JSON.stringify(cachedData) === JSON.stringify(currentData)) {
        console.log(`⏭️ Skipping update for ${deviceId} - data unchanged`);
        return;
    }

    // Update cache with new data
    sensorCardCache[deviceId] = currentData;

    console.log(`🔧 Updating card for ${deviceId}:`, data);

    const container = document.getElementById('sensor-cards');
    let card = document.getElementById(`card-${deviceId}`);

    if (!card) {
        card = document.createElement('div');
        card.className = 'card sensor-card';
        card.id = `card-${deviceId}`;
        container.appendChild(card);
        console.log(`✨ Created new card for ${deviceId}`);
    }

    const location = data.location || deviceId;
    const isOccupied = data.sim_occupancy === 1;
    const ledStatus = data.led_status ? 'led-on' : 'led-off';
    const manualMode = data.manual_override ? '<span class="manual-mode">MANUAL</span>' : '';

    // Check online status
    let isOnline = false;
    if (timestamp) {
        try {
            let timestampToUse = timestamp;
            if (!timestamp.includes('Z') && !timestamp.includes('+') && !timestamp.includes('-', 10)) {
                timestampToUse = timestamp + 'Z';
            }

            const deviceTime = new Date(timestampToUse).getTime();
            const currentTime = Date.now();
            const timeDiff = currentTime - deviceTime;

            isOnline = !isNaN(deviceTime) && timeDiff < 60000 && timeDiff >= 0;
        } catch (e) {
            console.error(`Device ${deviceId} timestamp parse error:`, e);
            isOnline = false;
        }
    }

    // Check if device has override
    fetchDeviceOverride(deviceId).then(override => {
        const overrideInfo = override?.active ? `
            <div class="override-info">
                <strong>Override Active:</strong> ${override.status.toUpperCase()}
                (${override.type}${override.expires_at ? ' - expires: ' + new Date(override.expires_at + 'Z').toLocaleString() : ''})
            </div>
        ` : '';

        card.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <h3 style="margin: 0;">
                    🏠 ${location.charAt(0).toUpperCase() + location.slice(1)}
                    <span class="led-status ${ledStatus}"></span>
                    ${manualMode}
                </h3>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div style="width: 10px; height: 10px; border-radius: 50%; background-color: ${isOnline ? '#27ae60' : '#e74c3c'};"></div>
                    <span style="font-size: 12px; color: ${isOnline ? '#27ae60' : '#e74c3c'}; font-weight: bold;">${isOnline ? 'Online' : 'Offline'}</span>
                </div>
            </div>

            <!-- Mode Indicators -->
            <div style="display: flex; gap: 8px; margin-bottom: 15px; flex-wrap: wrap;">
                <div style="padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; ${override?.active ? 'background: #fff3cd; color: #856404;' : 'background: #d4edda; color: #155724;'}">
                    ${override?.active ? '🔧 Manual Mode' : '🤖 Auto Mode'}
                </div>
                ${data.energy_saving_mode ? '<div style="padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; background: #d1ecf1; color: #0c5460;">💚 Energy Saving</div>' : ''}
                ${data.led_status ? '<div style="padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; background: #ffebcd; color: #8b4513;">💡 LED ON</div>' : ''}
            </div>

            <div class="sensor-data">
                <div class="sensor-value">
                    <div class="label">💡 Light</div>
                    <div class="value">${data.lux || 'N/A'} lux</div>
                </div>
                <div class="sensor-value">
                    <div class="label">👤 True Occupancy</div>
                    <div class="value">${isOccupied ? '✅ Yes' : '❌ No'}</div>
                </div>
                <div class="sensor-value">
                    <div class="label">🌡️ Temperature</div>
                    <div class="value">${data.temperature ? data.temperature.toFixed(1) : 'N/A'}°C</div>
                </div>
                <div class="sensor-value">
                    <div class="label">🔮 Predicted Temp</div>
                    <div class="value">${(data.predicted_temp !== undefined && data.predicted_temp !== null && data.predicted_temp > 0) ? data.predicted_temp.toFixed(1) + '°C' : 'N/A'}</div>
                </div>
                <div class="sensor-value">
                    <div class="label">🎯 Target Temp</div>
                    <div class="value">${(data.target_temp !== undefined && data.target_temp !== null && data.target_temp > 0) ? data.target_temp.toFixed(1) + '°C' : 'Not Set'}</div>
                </div>
                <div class="sensor-value">
                    <div class="label">💧 Humidity</div>
                    <div class="value">${data.humidity ? data.humidity.toFixed(1) : 'N/A'}%</div>
                </div>
                <div class="sensor-value">
                    <div class="label">🌬️ CO2</div>
                    <div class="value">${data.co2 ? data.co2.toFixed(0) : 'N/A'} ppm</div>
                </div>
                <div class="sensor-value">
                    <div class="label">⚡ Usage</div>
                    <div class="value">${(data.room_usage_wh !== undefined && data.room_usage_wh !== null ? data.room_usage_wh : (data.room_usage !== undefined && data.room_usage !== null ? data.room_usage * 1000 : 0)).toFixed(1)} Wh</div>
                </div>
                <div class="sensor-value">
                    <div class="label">🆔 Node ID</div>
                    <div class="value">${deviceId}</div>
                </div>
            </div>

            ${overrideInfo}

            <!-- Enhanced Control Buttons -->
            <div style="margin-top: 15px;">
                ${(deviceId === 'node1' || deviceId === 'node2' || deviceId === 'node3') ? `
                    <!-- Node1, Node2, Node3: Separate LED and Heating Controls -->
                    <div style="font-size: 14px; font-weight: bold; margin-bottom: 8px; color: #2c3e50;">💡 LED Control</div>
                    <div class="control-buttons">
                        <button class="btn btn-on" onclick="sendLedCommand('${deviceId}', 'on')" style="flex: 1;" ${!isOnline ? 'disabled' : ''}>💡 LED ON</button>
                        <button class="btn btn-off" onclick="sendLedCommand('${deviceId}', 'off')" style="flex: 1;" ${!isOnline ? 'disabled' : ''}>💡 LED OFF</button>
                    </div>

                    <div style="font-size: 14px; font-weight: bold; margin: 15px 0 8px 0; color: #2c3e50;">🔥 Heating Control</div>
                    <div class="control-buttons">
                        <button class="btn btn-success" onclick="sendHeatingCommand('${deviceId}', 'on')" style="flex: 1;" ${!isOnline ? 'disabled' : ''}>🔥 HEAT ON</button>
                        <button class="btn btn-danger" onclick="sendHeatingCommand('${deviceId}', 'off')" style="flex: 1;" ${!isOnline ? 'disabled' : ''}>❄️ HEAT OFF</button>
                    </div>
                ` : `
                    <!-- Other Nodes: Original LED Control -->
                    <div style="font-size: 14px; font-weight: bold; margin-bottom: 8px; color: #2c3e50;">💡 LED Control</div>
                    <div class="control-buttons">
                        <button class="btn btn-on" onclick="sendOverrideCommand('${deviceId}', 'on')" style="flex: 1;" ${!isOnline ? 'disabled' : ''}>💡 LED ON</button>
                        <button class="btn btn-off" onclick="sendOverrideCommand('${deviceId}', 'off')" style="flex: 1;" ${!isOnline ? 'disabled' : ''}>💡 LED OFF</button>
                    </div>
                `}

                <!-- Duration Selection (common for all) -->
                <div class="slider-container" style="margin-top: 10px;">
                    <label for="duration-${deviceId}">Duration:</label>
                    <input type="range" id="duration-${deviceId}" class="duration-slider" min="0" max="24" step="1" value="${localStorage.getItem(`duration-${deviceId}`) || '24'}" list="duration-ticks-${deviceId}" onchange="saveDuration('${deviceId}', this.value)" ${!isOnline ? 'disabled' : ''}>
                    <datalist id="duration-ticks-${deviceId}">
                        <option value="0" label="Permanent">
                        <option value="1" label="1h">
                        <option value="4" label="4h">
                        <option value="12" label="12h">
                        <option value="24" label="24h">
                    </datalist>
                    <div class="slider-labels">
                        <span>Permanent</span>
                        <span>1h</span>
                        <span>4h</span>
                        <span>12h</span>
                        <span>24h</span>
                    </div>
                </div>

                <div style="margin-top: 8px;">
                    <button class="btn" onclick="removeOverride('${deviceId}')" ${!override?.active || !isOnline ? 'disabled' : ''} style="width: 100%; background: #6c757d; color: white; opacity: ${override?.active && isOnline ? '1' : '0.6'};">
                        🤖 AUTO MODE
                    </button>
                </div>
            </div>

            <div class="timestamp">🕒 Last update: ${new Date().toLocaleTimeString()}</div>
        `;
    });
}
