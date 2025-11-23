/**
 * Control Page Configuration & State
 */

export const devices = {};
export const activityLogs = {};

export function addDevice(deviceId, data) {
    devices[deviceId] = data;
}

export function getDevice(deviceId) {
    return devices[deviceId];
}

export function getAllDevices() {
    return devices;
}

export function initActivityLog(deviceId) {
    if (!activityLogs[deviceId]) {
        activityLogs[deviceId] = [];
    }
}

export function addLogEntry(deviceId, message) {
    if (!activityLogs[deviceId]) {
        activityLogs[deviceId] = [];
    }

    const timestamp = new Date().toLocaleTimeString();
    activityLogs[deviceId].unshift({ timestamp, message });

    if (activityLogs[deviceId].length > 10) {
        activityLogs[deviceId] = activityLogs[deviceId].slice(0, 10);
    }

    const logContainer = document.getElementById(`log-entries-${deviceId}`);
    if (logContainer) {
        logContainer.innerHTML = activityLogs[deviceId]
            .map(entry => `<div class="log-entry"><span class="log-timestamp">${entry.timestamp}</span> ${entry.message}</div>`)
            .join('');
    }
}

export function getActivityLog(deviceId) {
    return activityLogs[deviceId] || [];
}
