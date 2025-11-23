/**
 * Statistics Module
 *
 * Manages statistics calculations and updates.
 */

import { currentDataPoints } from './config.js';
import { updateAllChartsWithHistorical } from './chartUpdates.js';

/**
 * Update statistics display
 */
export async function updateStatistics(dataPoints = null) {
    const points = dataPoints || currentDataPoints;
    const hours = points <= 24 ? points : 100; // 100 means "all data"

    try {
        const [statusResponse, historicalResponse] = await Promise.all([
            fetch('/api/status'),
            fetch(`/api/historical/${hours}`)
        ]);

        const statusData = await statusResponse.json();
        const historicalData = await historicalResponse.json();

        // Update statistics from historical data
        updateStatisticsFromHistorical(historicalData.data);

        // Update charts
        updateAllChartsWithHistorical(historicalData.data, statusData.latest_data);
    } catch (error) {
        console.error('Error fetching statistics:', error);
    }
}

/**
 * Calculate statistics from historical data
 */
export function updateStatisticsFromHistorical(historicalData) {
    let totalHeatingTime = 0;
    let totalTemperatureReadings = 0;
    let sumTemperatures = 0;
    let heatingOnCount = 0;
    let temperatureMeetingTarget = 0;

    // Group by device
    const deviceData = {};
    historicalData.forEach(d => {
        const deviceId = d.device_id;
        if (!deviceData[deviceId]) {
            deviceData[deviceId] = [];
        }
        deviceData[deviceId].push(d);
    });

    // Process each device
    Object.keys(deviceData).forEach(deviceId => {
        const deviceHistory = deviceData[deviceId];
        deviceHistory.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

        // Calculate heating statistics
        deviceHistory.forEach(d => {
            const heatingStatus = d.data.heating_status || d.data.led_status || 0;
            const temperature = d.data.temperature || 0;
            const targetTemp = d.data.target_temp || 0;

            // Count heating time (15 seconds per reading)
            if (heatingStatus === 1) {
                totalHeatingTime += 15; // seconds
                heatingOnCount++;
            }

            // Track temperature averages
            if (temperature > 0) {
                sumTemperatures += temperature;
                totalTemperatureReadings++;
            }

            // Track how often temperature meets target (within 1°C)
            if (targetTemp > 0 && Math.abs(temperature - targetTemp) <= 1) {
                temperatureMeetingTarget++;
            }
        });
    });

    // Calculate heating hours
    const heatingHours = totalHeatingTime / 3600;

    // Calculate average temperature
    const avgTemperature = totalTemperatureReadings > 0 ? sumTemperatures / totalTemperatureReadings : 0;

    // Calculate efficiency (percentage of time temperature meets target)
    const efficiency = totalTemperatureReadings > 0 ? (temperatureMeetingTarget / totalTemperatureReadings * 100) : 0;

    // Update display elements (check if they exist first)
    const heatingTimeElement = document.getElementById('total-heating-time');
    if (heatingTimeElement) {
        heatingTimeElement.textContent = heatingHours.toFixed(1);
    }

    const avgTempElement = document.getElementById('avg-temperature');
    if (avgTempElement) {
        avgTempElement.textContent = avgTemperature.toFixed(1);
    }

    const efficiencyElement = document.getElementById('efficiency');
    if (efficiencyElement) {
        efficiencyElement.textContent = efficiency.toFixed(1);
    }
}

/**
 * Update energy statistics
 */
export function updateEnergyStats(stats) {
    // Update heating time stats
    const heatingTimeElement = document.getElementById('total-heating-time');
    if (heatingTimeElement && stats.total_decisions) {
        // Approximate heating hours from decisions (1 decision every 30 min)
        const heatingHours = (stats.total_decisions * 0.5);
        heatingTimeElement.textContent = heatingHours.toFixed(1);
    }

    // Update average temperature (if available from latest data)
    const avgTempElement = document.getElementById('avg-temperature');
    if (avgTempElement && stats.avg_temperature !== undefined) {
        avgTempElement.textContent = stats.avg_temperature.toFixed(1);
    }

    // Update efficiency
    const efficiencyElement = document.getElementById('efficiency');
    if (efficiencyElement) {
        // Calculate efficiency as percentage of energy saved vs total consumption
        const totalEnergy = stats.baseline_energy || 1;
        const savedEnergy = stats.energy_saved || 0;
        const efficiency = totalEnergy > 0 ? (savedEnergy / totalEnergy * 100) : 0;
        efficiencyElement.textContent = efficiency.toFixed(1);
    }
}
