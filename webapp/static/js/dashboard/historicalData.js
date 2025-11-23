/**
 * Historical Data Management
 *
 * Functions for fetching and processing historical data, slider controls.
 */

import {
    currentDataPoints, currentMinutes, updateInterval,
    setCurrentDataPoints, setCurrentMinutes, setUpdateInterval,
    setSliderTimeout, sliderTimeout, setIsHistoricalMode
} from './config.js';
import {
    sliderToMinutes, minutesToDisplayString,
    interpolateDataPointsWithGaps, generateTimeLabels
} from './dataUtils.js';
import {
    energyChart, temperatureChart, predictionChart, heatingChart,
    updateDatasetForDevice, updateSimulatedOccupancyDataset
} from './charts.js';
import { chartPeaks } from './config.js';
import { updateStatus, updateHeatingStats } from './globalControls.js';

// Update data points when slider moves (debounced)
export function updateDataPoints(value) {
    const minutes = sliderToMinutes(parseInt(value));
    setCurrentMinutes(minutes);

    let targetPoints = Math.min(144, Math.max(10, Math.round(minutes * 4)));

    if (minutes === 30) targetPoints = 60;

    setCurrentDataPoints(targetPoints);
    setUpdateInterval(Math.round((minutes * 60 * 1000) / targetPoints));

    document.getElementById('slider-indicator-1').textContent = minutesToDisplayString(minutes);
    document.getElementById('slider-indicator-2').textContent = `${targetPoints} points`;
    document.getElementById('slider-indicator-3').textContent = '⏳ Updating...';
    document.getElementById('slider-indicator-3').style.color = '#ffa500';

    console.log(`📊 Slider updated: ${minutes} min, ${targetPoints} points, update every ${updateInterval/1000} seconds`);

    if (sliderTimeout) {
        clearTimeout(sliderTimeout);
    }

    const timeout = setTimeout(() => {
        console.log('🔄 Fetching historical data after slider debounce...');
        updateStatistics();
        setSliderTimeout(null);
    }, 1000);

    setSliderTimeout(timeout);
}

// Load and update statistics
export function updateStatistics() {
    const minutes = currentMinutes;
    const hours = Math.max(1, Math.ceil(minutes / 60));

    console.log(`📊 Fetching historical data for ${minutes} minutes (${hours} hours)`);

    fetch(`/api/historical/${hours}`)
    .then(response => response.json())
    .then(data => {
        console.log(`📊 Received ${data.data.length} historical data points`);
        updateAllChartsWithHistorical(data.data);
        document.getElementById('slider-indicator-3').textContent = '✅ Ready';
        document.getElementById('slider-indicator-3').style.color = '#27ae60';
    })
    .catch(error => {
        console.error('Error fetching historical data:', error);
        document.getElementById('slider-indicator-3').textContent = '❌ Error';
        document.getElementById('slider-indicator-3').style.color = '#e74c3c';
    });
}

// Update all charts with historical data
export function updateAllChartsWithHistorical(historicalData) {
    console.log('📊 Processing historical data:', historicalData);

    const targetPoints = currentDataPoints;
    const totalMinutes = currentMinutes;

    let maxEnergy = 10;
    let maxTemp = 15;
    let maxLight = 100;

    const deviceData = {};
    historicalData.forEach(item => {
        const deviceId = item.device_id;
        if (!deviceData[deviceId]) deviceData[deviceId] = [];
        deviceData[deviceId].push(item);
    });

    let totalConsumption = 0;
    let energySaved = 0;
    let timeLabels = null;

    Object.keys(deviceData).forEach(deviceId => {
        const data = deviceData[deviceId];
        console.log(`📊 Device ${deviceId}: ${data.length} data points`);

        if (data.length > 0) {
            data.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

            const dataWithTimestamps = data.map(d => {
                const payload = d.data || d;
                let timestamp = d.timestamp;
                if (timestamp && !timestamp.endsWith('Z') && !timestamp.includes('+')) {
                    timestamp = timestamp + 'Z';
                }
                return {
                    timestamp: new Date(timestamp),
                    energy: payload.room_usage_wh !== undefined
                        ? payload.room_usage_wh
                        : (payload.room_usage !== undefined ? payload.room_usage * 1000 : null),
                    temperature: payload.temperature !== undefined ? payload.temperature : null,
                    light: (payload.lux !== undefined || payload.light_level !== undefined) ? (payload.lux || payload.light_level) : null,
                    occupancy: payload.occupancy !== undefined ? payload.occupancy : null,
                    sim_occupancy: payload.sim_occupancy !== undefined ? payload.sim_occupancy : null
                };
            });

            // Calculate total energy consumption from room_usage_wh
            data.forEach(d => {
                const payload = d.data || d;
                totalConsumption += payload.room_usage_wh || 0;
            });

            // Note: Energy saving calculations removed for heating-focused dashboard
            // Heating optimization events are tracked differently than LED optimization

            dataWithTimestamps.forEach(d => {
                if (d.energy !== null && d.energy > maxEnergy) {
                    maxEnergy = d.energy;
                    if (maxEnergy > 20) maxEnergy = 20;
                }
                if (d.temperature !== null && d.temperature > maxTemp) {
                    maxTemp = d.temperature;
                }
                if (d.light !== null && d.light > maxLight) {
                    maxLight = d.light;
                }
            });

            const energyDataForInterp = dataWithTimestamps.map(d => ({ timestamp: d.timestamp, value: d.energy }));
            const tempDataForInterp = dataWithTimestamps.map(d => ({ timestamp: d.timestamp, value: d.temperature }));

            const energyInterp = interpolateDataPointsWithGaps(energyDataForInterp, targetPoints, totalMinutes);
            const tempInterp = interpolateDataPointsWithGaps(tempDataForInterp, targetPoints, totalMinutes);

            if (!timeLabels) {
                timeLabels = energyInterp.labels;
            }

            const location = data[0].data.location || deviceId;

            updateDatasetForDevice(energyChart, deviceId, energyInterp.data, location);
            updateDatasetForDevice(temperatureChart, deviceId, tempInterp.data, location);
            // Light and occupancy charts removed in heating-focused dashboard
        }
    });

    // Note: DOM elements for total-consumption and energy-saved removed in heating dashboard
    // These statistics are no longer displayed in the temperature control interface
    console.log(`📊 Total consumption: ${totalConsumption.toFixed(3)} Wh`);

    if (timeLabels) {
        energyChart.data.labels = timeLabels;
    } else {
        energyChart.data.labels = generateTimeLabels(targetPoints, totalMinutes);
    }
    temperatureChart.data.labels = [...energyChart.data.labels];
    predictionChart.data.labels = [...energyChart.data.labels];
    heatingChart.data.labels = [...energyChart.data.labels];

    chartPeaks.energy = Math.max(10, Math.ceil(maxEnergy * 1.1));
    chartPeaks.temperature = Math.max(30, Math.ceil(maxTemp + 2));

    energyChart.options.scales.y.max = chartPeaks.energy;
    temperatureChart.options.scales.y.max = chartPeaks.temperature;
    predictionChart.options.scales.y.max = 30;
    heatingChart.options.scales.y.max = 1.2;

    energyChart.update();
    temperatureChart.update();
    predictionChart.update();
    heatingChart.update();
}

// Return to real-time mode
export function returnToRealtime() {
    setIsHistoricalMode(false);
    console.log('🔄 Returned to real-time mode');

    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            updateStatus(data);
            if (data.latest_data) {
                updateHeatingStats(data.latest_data);
            }
        })
        .catch(error => console.error('Error refreshing status:', error));
}
