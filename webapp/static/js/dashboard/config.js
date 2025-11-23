/**
 * Dashboard Configuration & Global State
 *
 * Shared configuration values and state variables used across dashboard modules.
 */

// Peak value tracking for charts
export const chartPeaks = {
    energy: 10,        // Minimum scale for energy chart in Wh
    temperature: 30,   // Maximum scale for temperature chart
    light: 100,        // Maximum scale for light chart
    occupancy: 1.2     // Fixed scale for occupancy chart
};

// Cache for sensor card data to prevent unnecessary updates
export const sensorCardCache = {};

// Slider and data management
export let currentDataPoints = 60; // Default for 30 minutes
export let currentMinutes = 30;
export let updateInterval = 30000; // Default 30 seconds for 30 min range
export let lastChartUpdate = 0;
export let sliderTimeout = null; // For debouncing slider changes
export let isHistoricalMode = false; // Track if we're showing historical data

// Setters for mutable state
export function setCurrentDataPoints(value) {
    currentDataPoints = value;
}

export function setCurrentMinutes(value) {
    currentMinutes = value;
}

export function setUpdateInterval(value) {
    updateInterval = value;
}

export function setLastChartUpdate(value) {
    lastChartUpdate = value;
}

export function setSliderTimeout(value) {
    sliderTimeout = value;
}

export function setIsHistoricalMode(value) {
    isHistoricalMode = value;
}

// Color management for dynamic devices
export const colorPalette = ['#3498db', '#e74c3c', '#27ae60', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#34495e'];
export const deviceColors = {};

export function getDeviceColor(deviceId) {
    if (!deviceColors[deviceId]) {
        const index = Object.keys(deviceColors).length % colorPalette.length;
        deviceColors[deviceId] = colorPalette[index];
    }
    return deviceColors[deviceId];
}
