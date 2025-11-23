/**
 * Analytics Main Initialization
 *
 * Coordinates all analytics functionality with modular architecture.
 */

import { initializeCharts } from './charts.js';
import { updateStatistics } from './statistics.js';
import { generateInsights } from './insights.js';
import { currentDataPoints, setCurrentDataPoints, sliderTimeout, setSliderTimeout } from './config.js';
import { sliderToHours, hoursToDisplayString } from './dataUtils.js';
import {
    updateRoomConsumption,
    updateHourlyPattern,
    updateHistoricalChart,
    updateTemperatureTrend,
    updateLightAnalysis
} from './chartUpdates.js';

/**
 * Update system status indicators
 */
function updateStatus(status) {
    const mqttStatus = document.getElementById('mqtt-status');
    const dbStatus = document.getElementById('db-status');
    const aiStatus = document.getElementById('ai-status');
    const mqttText = document.getElementById('mqtt-text');
    const dbText = document.getElementById('db-text');
    const aiText = document.getElementById('ai-text');
    const nodesCount = document.getElementById('nodes-count');

    if (mqttStatus && mqttText) {
        mqttStatus.className = `status-indicator ${status.system_status.mqtt_connected ? 'status-online' : 'status-offline'}`;
        mqttText.textContent = status.system_status.mqtt_connected ? 'Connected' : 'Disconnected';
    }

    if (dbStatus && dbText) {
        dbStatus.className = `status-indicator ${status.system_status.db_connected ? 'status-online' : 'status-offline'}`;
        dbText.textContent = status.system_status.db_connected ? 'Connected' : 'Disconnected';
    }

    // Update heating system status
    const heatingActive = Object.values(status.latest_data || {}).some(device =>
        device.data && device.data.heating_status === 1
    );
    if (aiStatus && aiText) {
        aiStatus.className = `status-indicator ${heatingActive ? 'status-online' : 'status-offline'}`;
        aiText.textContent = heatingActive ? 'Active' : 'Standby';
    }

    if (nodesCount) {
        nodesCount.textContent = status.system_status.nodes_online || 0;
    }
}

/**
 * Update all charts with historical data
 */
async function updateAllChartsWithHistorical(historicalData, latestData) {
    if (!historicalData || historicalData.length === 0) {
        console.warn('No historical data available');
        return;
    }

    try {
        // Update all charts in parallel
        await Promise.all([
            updateRoomConsumption(historicalData),
            updateHourlyPattern(historicalData),
            updateHistoricalChart(historicalData),
            updateTemperatureTrend(historicalData),
            updateLightAnalysis(historicalData),
        ]);

        // Generate insights
        generateInsights(historicalData);
    } catch (error) {
        console.error('Error updating charts:', error);
    }
}

/**
 * Handle time slider change
 */
function onTimeSliderChange() {
    const slider = document.getElementById('data-points-slider');
    if (!slider) {
        console.error('Time slider element not found');
        return;
    }

    const value = parseInt(slider.value);
    const hours = sliderToHours(value);

    setCurrentDataPoints(value);

    // Update display
    const displayEl = document.getElementById('data-points-display');
    if (displayEl) {
        displayEl.textContent = hoursToDisplayString(hours);
    }

    // Debounce updates
    if (sliderTimeout) {
        clearTimeout(sliderTimeout);
    }

    const timeout = setTimeout(() => {
        updateStatistics(value);
        setSliderTimeout(null);
    }, 500);

    setSliderTimeout(timeout);
}

/**
 * Initialize the analytics page
 */
function initializePage() {
    console.log('📊 Initializing Analytics Page...');

    // Initialize charts
    initializeCharts();

    // Set up time slider
    const slider = document.getElementById('data-points-slider');
    if (slider) {
        slider.value = currentDataPoints;
        slider.addEventListener('input', onTimeSliderChange);

        // Update initial display
        const hours = sliderToHours(currentDataPoints);
        const displayEl = document.getElementById('data-points-display');
        if (displayEl) {
            displayEl.textContent = hoursToDisplayString(hours);
        }
    }

    // Fetch initial status
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            console.log('📊 Initial status received:', data);
            updateStatus(data);
        })
        .catch(error => console.error('❌ Error fetching initial status:', error));

    // Set up periodic status updates
    setInterval(() => {
        fetch('/api/status')
            .then(response => response.json())
            .then(data => {
                updateStatus(data);
            })
            .catch(error => console.error('❌ Error in status update:', error));
    }, 5000);

    // Initial data load
    updateStatistics();

    console.log('📈 Analytics page initialized');
}

// Expose functions to window for HTML handlers
window.updateStatistics = updateStatistics;
window.onTimeSliderChange = onTimeSliderChange;
window.updateDataPoints = function(value) {
    // Called from HTML oninput handler
    const numValue = parseInt(value);
    const hours = sliderToHours(numValue);

    setCurrentDataPoints(numValue);

    // Update display
    const displayEl = document.getElementById('data-points-display');
    if (displayEl) {
        displayEl.textContent = hoursToDisplayString(hours);
    }

    // Debounce updates
    if (sliderTimeout) {
        clearTimeout(sliderTimeout);
    }

    const timeout = setTimeout(() => {
        updateStatistics(numValue);
        setSliderTimeout(null);
    }, 500);

    setSliderTimeout(timeout);
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', initializePage);
