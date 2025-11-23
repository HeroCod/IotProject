/**
 * Analytics Configuration & Global State
 */

// Chart instances
export let roomChart, hourlyChart, historicalChart;

export function setRoomChart(chart) { roomChart = chart; }
export function setHourlyChart(chart) { hourlyChart = chart; }
export function setHistoricalChart(chart) { historicalChart = chart; }

// State management
export let currentDataPoints = 20;
export let lastUpdateTime = 0;
export let updateInterval = 5000;
export let sliderTimeout = null;
export let isHistoricalMode = false;

export function setCurrentDataPoints(value) { currentDataPoints = value; }
export function setLastUpdateTime(value) { lastUpdateTime = value; }
export function setUpdateInterval(value) { updateInterval = value; }
export function setSliderTimeout(value) { sliderTimeout = value; }
export function setIsHistoricalMode(value) { isHistoricalMode = value; }

// Peak value tracking
export const chartPeaks = {
    historical: 0.2,
    hourly: 0.1
};

// Color management
export const colorPalette = ['#3498db', '#e74c3c', '#27ae60', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#34495e'];
export const deviceColors = {};

export function getDeviceColor(deviceId) {
    if (!deviceColors[deviceId]) {
        const index = Object.keys(deviceColors).length % colorPalette.length;
        deviceColors[deviceId] = colorPalette[index];
    }
    return deviceColors[deviceId];
}
