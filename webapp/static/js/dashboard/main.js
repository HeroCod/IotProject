/**
 * Dashboard Main Initialization
 *
 * Main entry point for the heating management dashboard - coordinates all modules.
 */

import { setLastChartUpdate, setIsHistoricalMode } from './config.js';
import { initializeCharts, toggleSimulatedOccupancy, resetChartScales } from './charts.js';
import {
    updateStatus, updateHeatingStats, globalCommand,
    globalLightCommand, globalHeatingCommand,
    refreshSystem, clearAllOverrides, setQuickTemp,
    showSystemStatus, loadPresetSchedule, uploadSchedule,
    clearHistoricalData, forceClockSync
} from './globalControls.js';
import { updateSensorCard } from './sensorCards.js';
import {
    sendOverrideCommand, sendLedCommand, sendHeatingCommand,
    removeOverride, saveDuration
} from './deviceControls.js';
import { updateDataPoints, updateStatistics } from './historicalData.js';
import { setupSocketHandlers } from './socketHandlers.js';

// Initialize the page
function initializePage() {
    console.log('🚀 Initializing Smart Heating Dashboard...');

    // Initialize charts
    initializeCharts();

    // Initialize socket handlers
    setupSocketHandlers();

    // Initialize chart update timing
    setLastChartUpdate(Date.now());
    setIsHistoricalMode(false);

    // Restore slider setting from localStorage
    const savedDataPoints = localStorage.getItem('dataPoints');
    if (savedDataPoints) {
        const slider = document.getElementById('data-points-slider');
        if (slider) {
            slider.value = savedDataPoints;
            console.log('📊 Restored slider to saved value:', savedDataPoints);
            updateDataPoints(savedDataPoints);
        }
    }

    // Fetch initial data
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            console.log('📊 Initial data received:', data);
            updateStatus(data);
            updateHeatingStats(data.latest_data || {});

            // Display initial sensor data
            Object.entries(data.latest_data || {}).forEach(([deviceId, deviceInfo]) => {
                console.log(`📡 Initializing device: ${deviceId}`, deviceInfo);
                updateSensorCard(deviceId, deviceInfo.data, deviceInfo.timestamp, deviceInfo.type);
            });

            // Load historical data for charts
            updateStatistics();

            // Simulate slider move to ensure correct graph display
            setTimeout(() => {
                const slider = document.getElementById('data-points-slider');
                if (slider) {
                    console.log('🔄 Simulating slider move to ensure correct graph display');
                    updateDataPoints(slider.value);
                }
            }, 500);
        })
        .catch(error => console.error('❌ Error fetching initial data:', error));

    // Set up real-time status updates
    setInterval(() => {
        fetch('/api/status')
            .then(response => response.json())
            .then(data => {
                console.log('🔄 Status-only update:', new Date().toLocaleTimeString());
                updateStatus(data);
                updateHeatingStats(data.latest_data || {});
            })
            .catch(error => console.error('❌ Error in status update:', error));
    }, 5000);
}

// Make functions available globally for onclick handlers in HTML
window.updateDataPoints = updateDataPoints;
window.toggleSimulatedOccupancy = toggleSimulatedOccupancy;
window.sendOverrideCommand = sendOverrideCommand;
window.sendLedCommand = sendLedCommand;
window.sendHeatingCommand = sendHeatingCommand;
window.removeOverride = removeOverride;
window.saveDuration = saveDuration;
window.globalCommand = globalCommand;
window.globalLightCommand = globalLightCommand;
window.globalHeatingCommand = globalHeatingCommand;
window.refreshSystem = refreshSystem;
window.clearAllOverrides = clearAllOverrides;
window.setQuickTemp = setQuickTemp;
window.showSystemStatus = showSystemStatus;
window.loadPresetSchedule = loadPresetSchedule;
window.uploadSchedule = uploadSchedule;
window.clearHistoricalData = clearHistoricalData;
window.forceClockSync = forceClockSync;
window.resetChartScales = resetChartScales;

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    initializePage();
});
