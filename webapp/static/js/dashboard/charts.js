/**
 * Chart Management
 *
 * Chart.js configuration and update functions for heating management dashboard.
 */

import { chartPeaks, getDeviceColor, currentDataPoints } from './config.js';
import { shiftColorHue, hexToRgba } from './dataUtils.js';

// Chart instances (exported for use in other modules)
export let energyChart;
export let temperatureChart;
export let predictionChart;
export let heatingChart;

// Initialize all charts
export function initializeCharts() {
    energyChart = createEnergyChart();
    temperatureChart = createTemperatureChart();
    predictionChart = createPredictionChart();
    heatingChart = createHeatingChart();
}

// Create Energy Chart (Heating Energy Consumption)
function createEnergyChart() {
    const ctx = document.getElementById('energyChart').getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: []
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 1000,
                easing: 'easeInOutQuart'
            },
            layout: {
                padding: {
                    bottom: 20,
                    left: 10,
                    right: 10
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 2000,
                    title: {
                        display: true,
                        text: 'Heating Power (W)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Time'
                    },
                    ticks: {
                        maxTicksLimit: 10
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            },
            elements: {
                point: {
                    radius: 3,
                    hoverRadius: 6
                }
            }
        }
    });
}

// Create Temperature Chart
function createTemperatureChart() {
    const tempCtx = document.getElementById('temperatureChart').getContext('2d');
    return new Chart(tempCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: []
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 1000,
                easing: 'easeInOutQuart'
            },
            layout: {
                padding: {
                    bottom: 20,
                    left: 10,
                    right: 10
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    min: 10,
                    max: chartPeaks.temperature,
                    title: {
                        display: true,
                        text: 'Temperature (°C)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Time'
                    },
                    ticks: {
                        maxTicksLimit: 10
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            },
            elements: {
                point: {
                    radius: 3,
                    hoverRadius: 6
                }
            }
        }
    });
}

// Create Prediction Chart (Temperature Prediction & Target)
function createPredictionChart() {
    const predCtx = document.getElementById('predictionChart').getContext('2d');
    return new Chart(predCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: []
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 1000,
                easing: 'easeInOutQuart'
            },
            layout: {
                padding: {
                    bottom: 20,
                    left: 10,
                    right: 10
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    min: 10,
                    max: 30,
                    title: {
                        display: true,
                        text: 'Temperature (°C)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Time'
                    },
                    ticks: {
                        maxTicksLimit: 10
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            },
            elements: {
                point: {
                    radius: 3,
                    hoverRadius: 6
                }
            }
        }
    });
}

// Create Heating Status Chart
function createHeatingChart() {
    const heatCtx = document.getElementById('heatingChart').getContext('2d');
    return new Chart(heatCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: []
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 1000,
                easing: 'easeInOutQuart'
            },
            layout: {
                padding: {
                    bottom: 20,
                    left: 10,
                    right: 10
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 1.5,
                    ticks: {
                        stepSize: 0.5,
                        callback: function(value) {
                            return value === 1 ? 'ON' : value === 0 ? 'OFF' : '';
                        }
                    },
                    title: {
                        display: true,
                        text: 'Heating Status'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Time'
                    },
                    ticks: {
                        maxTicksLimit: 10
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            },
            elements: {
                point: {
                    radius: 3,
                    hoverRadius: 6
                },
                line: {
                    stepped: true  // Show as step chart for on/off status
                }
            }
        }
    });
}

// Update dataset for a specific device
export function updateDatasetForDevice(chart, deviceId, data, label) {
    let dataset = chart.data.datasets.find(d => d.deviceId === deviceId);
    if (!dataset) {
        const color = getDeviceColor(deviceId);
        dataset = {
            label: label,
            deviceId: deviceId,
            data: data,
            borderColor: color,
            backgroundColor: color + '40',
            tension: 0.4,
            fill: true,
            spanGaps: false
        };
        chart.data.datasets.push(dataset);
    } else {
        if (data && data.length > 0) {
            dataset.data = data;
        }
        if (label) {
            dataset.label = label;
        }
    }
}

// Update simulated occupancy dataset
export function updateSimulatedOccupancyDataset(chart, deviceId, data, label) {
    const simulatedId = `${deviceId}_simulated`;
    let dataset = chart.data.datasets.find(d => d.deviceId === simulatedId);

    if (!dataset) {
        const baseColor = getDeviceColor(deviceId);
        const simulatedColor = shiftColorHue(baseColor, 60);

        dataset = {
            label: `${label} (Ground Truth)`,
            deviceId: simulatedId,
            data: data,
            borderColor: simulatedColor,
            backgroundColor: hexToRgba(simulatedColor, 0.1),
            borderWidth: 3,
            borderDash: [8, 4],
            tension: 0.2,
            fill: true,
            fillOpacity: 0.1,
            stepped: true,
            hidden: !isSimulatedOccupancyVisible(),
            yAxisID: 'y-simulated',
            pointRadius: 4,
            pointBackgroundColor: simulatedColor,
            pointBorderColor: '#ffffff',
            pointBorderWidth: 2,
            pointHoverRadius: 6,
            spanGaps: false
        };
        chart.data.datasets.push(dataset);
    } else {
        if (data && data.length > 0) {
            dataset.data = data;
        }
        if (label) {
            dataset.label = `${label}`;
        }
        dataset.hidden = !isSimulatedOccupancyVisible();
    }
}

// Check if simulated occupancy should be visible
export function isSimulatedOccupancyVisible() {
    const toggle = document.getElementById('toggle-simulated-occupancy');
    return toggle ? toggle.checked : false;
}

// Toggle simulated occupancy visibility
export function toggleSimulatedOccupancy() {
    const isVisible = isSimulatedOccupancyVisible();

    occupancyChart.data.datasets.forEach(dataset => {
        if (dataset.deviceId && dataset.deviceId.endsWith('_simulated')) {
            dataset.hidden = !isVisible;
        }
    });

    occupancyChart.update();
    localStorage.setItem('showSimulatedOccupancy', isVisible);
}

// Reset chart scales to default values
export function resetChartScales() {
    chartPeaks.energy = 20.0;
    chartPeaks.temperature = 50;
    chartPeaks.light = 500;
    chartPeaks.occupancy = 1.2;

    energyChart.options.scales.y.max = chartPeaks.energy;
    temperatureChart.options.scales.y.max = chartPeaks.temperature;
    lightChart.options.scales.y.max = chartPeaks.light;

    energyChart.update();
    temperatureChart.update();
    lightChart.update();
    occupancyChart.update();
}

// Update chart with real-time data (HEATING FOCUS)
export function updateChartRealtime(deviceId, data, timestamp) {
    console.log('📊 updateChart called for', deviceId, 'with data:', data);

    let utcTimestamp = timestamp;
    if (utcTimestamp && !utcTimestamp.endsWith('Z') && !utcTimestamp.includes('+')) {
        utcTimestamp = utcTimestamp + 'Z';
    }
    const time = utcTimestamp ? new Date(utcTimestamp).toLocaleTimeString() : new Date().toLocaleTimeString();

    // Extract heating-focused data
    // Prefer room_usage_wh (in Wh), fallback to room_usage * 1000 if only kWh available
    const consumption = data.room_usage_wh !== undefined && data.room_usage_wh !== null
        ? data.room_usage_wh
        : (data.room_usage !== undefined && data.room_usage !== null ? data.room_usage * 1000 : 0);
    const temperature = data.temperature !== undefined && data.temperature !== null ? data.temperature : null;
    const predictedTemp = data.predicted_temp !== undefined && data.predicted_temp !== null ? data.predicted_temp : null;
    const targetTemp = data.target_temp !== undefined && data.target_temp !== null ? data.target_temp : null;
    const heatingStatus = data.heating_status !== undefined && data.heating_status !== null ? data.heating_status : null;

    console.log('📊 Heating data - temp:', temperature, 'pred:', predictedTemp, 'target:', targetTemp, 'heating:', heatingStatus);

    // Update peak values for energy
    if (consumption !== null && consumption > chartPeaks.energy) {
        chartPeaks.energy = Math.ceil(consumption * 1.1);
        energyChart.options.scales.y.max = chartPeaks.energy;
    }

    // Update temperature chart peak
    if (temperature !== null && temperature > chartPeaks.temperature) {
        chartPeaks.temperature = Math.ceil(temperature + 2);
        temperatureChart.options.scales.y.max = chartPeaks.temperature;
    }

    const label = data.location || deviceId;

    // Update Energy Chart (Heating Power)
    updateDatasetForDevice(energyChart, deviceId, [], label);
    let energyDataset = energyChart.data.datasets.find(d => d.deviceId === deviceId);
    energyDataset.data.push(consumption);
    if (energyDataset.data.length > currentDataPoints) {
        energyDataset.data.shift();
    }

    // Update Temperature Chart - Show current, predicted, and target for each node
    // Current temperature
    updateDatasetForDevice(temperatureChart, `${deviceId}_current`, [], `${label} - Current`);
    let currentTempDataset = temperatureChart.data.datasets.find(d => d.deviceId === `${deviceId}_current`);
    if (currentTempDataset) {
        currentTempDataset.data.push(temperature);
        if (currentTempDataset.data.length > currentDataPoints) {
            currentTempDataset.data.shift();
        }
    }

    // Predicted temperature
    if (predictedTemp !== null) {
        updateDatasetForDevice(temperatureChart, `${deviceId}_predicted`, [], `${label} - Predicted`);
        let predTempDataset = temperatureChart.data.datasets.find(d => d.deviceId === `${deviceId}_predicted`);
        if (predTempDataset) {
            predTempDataset.borderDash = [5, 5];  // Dashed line for predicted
            predTempDataset.data.push(predictedTemp);
            if (predTempDataset.data.length > currentDataPoints) {
                predTempDataset.data.shift();
            }
        }
    }

    // Target temperature
    if (targetTemp !== null && targetTemp > 0) {
        updateDatasetForDevice(temperatureChart, `${deviceId}_target`, [], `${label} - Target`);
        let targetTempDataset = temperatureChart.data.datasets.find(d => d.deviceId === `${deviceId}_target`);
        if (targetTempDataset) {
            targetTempDataset.borderDash = [10, 5];  // Different dash pattern for target
            targetTempDataset.borderWidth = 2;
            targetTempDataset.data.push(targetTemp);
            if (targetTempDataset.data.length > currentDataPoints) {
                targetTempDataset.data.shift();
            }
        }
    }

    // Update Prediction Chart (Predicted & Target Temperature)
    if (predictedTemp !== null || targetTemp !== null) {
        // Predicted temperature dataset
        updateDatasetForDevice(predictionChart, `${deviceId}_predicted`, [], `${label} - Predicted`);
        let predDataset = predictionChart.data.datasets.find(d => d.deviceId === `${deviceId}_predicted`);
        if (predDataset) {
            predDataset.data.push(predictedTemp);
            if (predDataset.data.length > currentDataPoints) {
                predDataset.data.shift();
            }
        }

        // Target temperature dataset
        updateDatasetForDevice(predictionChart, `${deviceId}_target`, [], `${label} - Target`);
        let targetDataset = predictionChart.data.datasets.find(d => d.deviceId === `${deviceId}_target`);
        if (targetDataset) {
            targetDataset.borderDash = [5, 5];  // Dashed line for target
            targetDataset.data.push(targetTemp);
            if (targetDataset.data.length > currentDataPoints) {
                targetDataset.data.shift();
            }
        }
    }

    // Update Heating Status Chart
    if (heatingStatus !== null) {
        updateDatasetForDevice(heatingChart, deviceId, [], `${label} - Heating`);
        let heatingDataset = heatingChart.data.datasets.find(d => d.deviceId === deviceId);
        if (heatingDataset) {
            heatingDataset.data.push(heatingStatus);
            if (heatingDataset.data.length > currentDataPoints) {
                heatingDataset.data.shift();
            }
        }
    }

    // Update labels
    energyChart.data.labels.push(time);
    if (energyChart.data.labels.length > currentDataPoints) {
        energyChart.data.labels.shift();
    }

    temperatureChart.data.labels = [...energyChart.data.labels];
    predictionChart.data.labels = [...energyChart.data.labels];
    heatingChart.data.labels = [...energyChart.data.labels];

    console.log('📊 Updating heating charts...');
    energyChart.update('none');
    temperatureChart.update('none');
    predictionChart.update('none');
    heatingChart.update('none');
    console.log('📊 Charts updated');
}
