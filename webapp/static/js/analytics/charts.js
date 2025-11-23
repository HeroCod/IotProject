/**
 * Analytics Charts Initialization
 */

import { chartPeaks } from './config.js';

// Export chart instances
export let roomChart, hourlyChart, historicalChart;
export let temperatureTrendChart, lightAnalysisChart;

export function initializeCharts() {
    roomChart = initializeRoomChart();
    hourlyChart = initializeHourlyChart();
    historicalChart = initializeHistoricalChart();
    temperatureTrendChart = initializeTemperatureChart();
    lightAnalysisChart = initializeLightChart();
}

function initializeRoomChart() {
    const ctx = document.getElementById('roomConsumptionChart').getContext('2d');
    return new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: [],
            datasets: [{
                data: [],
                backgroundColor: ['#3498db', '#e74c3c', '#27ae60', '#f39c12', '#9b59b6', '#1abc9c'],
                borderWidth: 2,
                borderColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            }
        }
    });
}

function initializeHourlyChart() {
    const ctx = document.getElementById('hourlyPatternChart').getContext('2d');
    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels: Array.from({length: 24}, (_, i) => `${i}:00`),
            datasets: [{
                label: 'Average Consumption',
                data: new Array(24).fill(0),
                backgroundColor: '#3498db',
                borderColor: '#2980b9',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: chartPeaks.hourly,
                    title: {
                        display: true,
                        text: 'Energy (kWh)'
                    }
                }
            }
        }
    });
}

function initializeHistoricalChart() {
    const ctx = document.getElementById('historicalChart').getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: []
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: chartPeaks.historical,
                    title: {
                        display: true,
                        text: 'Energy Consumption (kWh)'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true
                }
            }
        }
    });
}

function initializeTemperatureChart() {
    const ctx = document.getElementById('temperatureTrendChart').getContext('2d');
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
            scales: {
                y: {
                    beginAtZero: false,
                    min: 15,
                    max: 35,
                    title: {
                        display: true,
                        text: 'Temperature (°C)'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            }
        }
    });
}

function initializeLightChart() {
    const ctx = document.getElementById('lightAnalysisChart').getContext('2d');
    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Morning', 'Noon', 'Afternoon', 'Evening', 'Night'],
            datasets: [{
                label: 'Average Light Level',
                data: [0, 0, 0, 0, 0],
                backgroundColor: ['#f39c12', '#f1c40f', '#e67e22', '#8e44ad', '#2c3e50']
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Light Level (Lux)' }
                }
            }
        }
    });
}


