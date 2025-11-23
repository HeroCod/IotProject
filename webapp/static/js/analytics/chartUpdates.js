/**
 * Chart Updates Module
 *
 * Manages all chart update functions for the analytics page.
 */

import { chartPeaks, getDeviceColor, currentDataPoints } from './config.js';
import { sliderToHours, interpolateDataPoints, generateTimeLabels } from './dataUtils.js';
import {
    roomChart, hourlyChart, historicalChart,
    temperatureTrendChart, lightAnalysisChart
} from './charts.js';

/**
 * Update all charts with historical data
 */
export async function updateAllChartsWithHistorical(historicalData, latestData) {
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
            updateLightAnalysis(historicalData)
        ]);
    } catch (error) {
        console.error('Error updating charts:', error);
    }
}


/**
 * Update room consumption pie chart
 */
export function updateRoomConsumption(historicalData) {
    if (!roomChart) {
        console.warn('Room chart not initialized');
        return;
    }

    const deviceToLocation = {};
    const roomConsumption = {};

    // Build location mapping and aggregate consumption
    historicalData.forEach(d => {
        const deviceId = d.device_id;
        const location = d.data.location || deviceId;
        const consumption = d.data.room_usage || 0;

        deviceToLocation[deviceId] = location;

        if (!roomConsumption[location]) {
            roomConsumption[location] = 0;
        }
        roomConsumption[location] += consumption;
    });

    // Update chart
    const locations = Object.keys(roomConsumption);
    const values = Object.values(roomConsumption).map(v => Math.round(v * 1000) / 1000);

    roomChart.data.labels = locations;
    if (roomChart.data.datasets[0]) {
        roomChart.data.datasets[0].data = values;
        roomChart.data.datasets[0].backgroundColor = locations.map((_, i) => getDeviceColor(`room${i}`));
    }
    roomChart.update();
}

/**
 * Update hourly pattern bar chart
 */
export function updateHourlyPattern(historicalData) {
    if (!hourlyChart) {
        console.warn('Hourly chart not initialized');
        return;
    }

    const hourlyData = new Array(24).fill(0);
    const hourlyCounts = new Array(24).fill(0);

    historicalData.forEach(d => {
        const hour = new Date(d.timestamp).getHours();
        const consumption = d.data.room_usage || 0;

        hourlyData[hour] += consumption;
        hourlyCounts[hour]++;
    });

    // Calculate averages
    for (let i = 0; i < 24; i++) {
        if (hourlyCounts[i] > 0) {
            hourlyData[i] = hourlyData[i] / hourlyCounts[i];

            // Update peak value
            if (hourlyData[i] > chartPeaks.hourly) {
                chartPeaks.hourly = Math.ceil(hourlyData[i] * 1.1 * 10) / 10;
                hourlyChart.options.scales.y.max = chartPeaks.hourly;
            }
        }
    }

    if (hourlyChart.data.datasets[0]) {
        hourlyChart.data.datasets[0].data = hourlyData;
    }
    hourlyChart.update();
}

/**
 * Update historical trends line chart
 */
export async function updateHistoricalChart(historicalData) {
    if (!historicalChart) {
        console.warn('Historical chart not initialized');
        return;
    }

    // Get device locations from API
    const locations = await getDeviceLocations();

    // Build device to location mapping
    const deviceToLocation = {};
    const uniqueLocations = new Set();

    historicalData.forEach(d => {
        const deviceId = d.device_id;
        const location = d.data.location || locations[deviceId] || deviceId;
        deviceToLocation[deviceId] = location;
        uniqueLocations.add(location);
    });

    const locationArray = Array.from(uniqueLocations);

    // Initialize data structures for each location
    const deviceData = {};
    locationArray.forEach((location, index) => {
        deviceData[`location_${index}`] = {
            labels: [],
            data: []
        };
    });

    // Sort and group data by location
    const sortedData = historicalData.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

    sortedData.forEach(d => {
        const deviceId = d.device_id;
        const locationKey = `location_${locationArray.indexOf(deviceToLocation[deviceId])}`;

        if (deviceData[locationKey]) {
            const timestamp = new Date(d.timestamp).toLocaleTimeString();
            const consumption = d.data.room_usage || 0;

            deviceData[locationKey].labels.push(timestamp);
            deviceData[locationKey].data.push(consumption);

            // Update peak value
            if (consumption > chartPeaks.historical) {
                chartPeaks.historical = Math.ceil(consumption * 1.1 * 10) / 10;
                historicalChart.options.scales.y.max = chartPeaks.historical;
            }
        }
    });

    // Get target data points
    const actualHours = sliderToHours(currentDataPoints);
    const minDataPoints = 10;
    const maxDataPoints = 200;
    const targetDataPoints = Math.min(maxDataPoints, Math.max(minDataPoints, Math.round(actualHours / 2)));

    // Process each location
    const processedData = {};
    Object.keys(deviceData).forEach(locationKey => {
        const originalData = deviceData[locationKey].data;
        const originalLabels = deviceData[locationKey].labels;

        if (originalData.length === 0) {
            processedData[locationKey] = {
                data: new Array(targetDataPoints).fill(0),
                labels: generateTimeLabels(targetDataPoints, actualHours)
            };
        } else if (originalData.length >= targetDataPoints) {
            const step = Math.floor(originalData.length / targetDataPoints);
            const sampledData = [];
            const sampledLabels = [];

            for (let i = 0; i < targetDataPoints; i++) {
                const index = Math.min(i * step, originalData.length - 1);
                sampledData.push(originalData[index]);
                sampledLabels.push(originalLabels[index]);
            }

            processedData[locationKey] = {
                data: sampledData,
                labels: sampledLabels
            };
        } else {
            processedData[locationKey] = interpolateDataPoints(
                originalData,
                originalLabels,
                targetDataPoints,
                actualHours
            );
        }
    });

    // Calculate dynamic tension
    let dynamicTension = 0.4;
    if (targetDataPoints < 20) dynamicTension = 0.2;
    else if (targetDataPoints < 50) dynamicTension = 0.4;
    else if (targetDataPoints < 100) dynamicTension = 0.6;
    else dynamicTension = 0.8;

    // Update chart
    historicalChart.data.labels = processedData.location_0 ? processedData.location_0.labels : generateTimeLabels(targetDataPoints, actualHours);
    historicalChart.data.datasets = [];

    const colors = ['#3498db', '#e74c3c', '#27ae60'];
    locationArray.forEach((location, index) => {
        const locationKey = `location_${index}`;
        const colorIndex = index % 3;

        historicalChart.data.datasets.push({
            label: location,
            data: processedData[locationKey] ? processedData[locationKey].data : new Array(targetDataPoints).fill(0),
            borderColor: colors[colorIndex],
            backgroundColor: colors[colorIndex].replace(')', ', 0.1)'),
            tension: dynamicTension
        });
    });

    historicalChart.update();
}

/**
 * Update temperature trend chart
 */
export function updateTemperatureTrend(historicalData) {
    if (!temperatureTrendChart) {
        console.warn('Temperature chart not initialized');
        return;
    }

    const tempData = [];
    const labels = [];

    historicalData.forEach(d => {
        const temp = d.data.temperature;
        if (temp !== undefined) {
            labels.push(new Date(d.timestamp).toLocaleTimeString());
            tempData.push(temp);
        }
    });

    // Initialize dataset if it doesn't exist
    if (!temperatureTrendChart.data.datasets[0]) {
        temperatureTrendChart.data.datasets.push({
            label: 'Temperature',
            data: tempData,
            borderColor: '#e74c3c',
            backgroundColor: 'rgba(231, 76, 60, 0.1)',
            tension: 0.4,
            fill: false
        });
    } else {
        temperatureTrendChart.data.datasets[0].data = tempData;
    }

    temperatureTrendChart.data.labels = labels;
    temperatureTrendChart.update();
}

/**
 * Update light analysis chart
 */
export function updateLightAnalysis(historicalData) {
    if (!lightAnalysisChart) {
        console.warn('Light analysis chart not initialized');
        return;
    }

    const lightData = [0, 0, 0, 0, 0]; // Morning, Noon, Afternoon, Evening, Night
    const lightCounts = [0, 0, 0, 0, 0];

    historicalData.forEach(d => {
        const hour = new Date(d.timestamp).getHours();
        const light = d.data.lux || 50;

        let timeSlot;
        if (hour >= 6 && hour < 10) timeSlot = 0;
        else if (hour >= 10 && hour < 14) timeSlot = 1;
        else if (hour >= 14 && hour < 18) timeSlot = 2;
        else if (hour >= 18 && hour < 22) timeSlot = 3;
        else timeSlot = 4;

        lightData[timeSlot] += light;
        lightCounts[timeSlot]++;
    });

    // Calculate averages
    const defaults = [45, 85, 70, 30, 15];
    for (let i = 0; i < 5; i++) {
        if (lightCounts[i] > 0) {
            lightData[i] = Math.round(lightData[i] / lightCounts[i]);
        } else {
            lightData[i] = defaults[i];
        }
    }

    if (lightAnalysisChart.data.datasets[0]) {
        lightAnalysisChart.data.datasets[0].data = lightData;
        lightAnalysisChart.update();
    }
}


/**
 * Get device locations from API
 */
async function getDeviceLocations() {
    try {
        const response = await fetch('/api/device-locations');
        if (response.ok) {
            return await response.json();
        }
    } catch (error) {
        console.warn('Failed to fetch device locations from API:', error);
    }
    return {};
}
