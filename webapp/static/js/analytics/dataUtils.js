/**
 * Analytics Data Utilities
 */

// Convert slider value to hours using logarithmic scale
export function sliderToHours(sliderValue) {
    if (sliderValue >= 100) {
        return 10000;
    } else if (sliderValue >= 50) {
        const yearHours = 8760;
        const maxHours = 10000;
        const ratio = (sliderValue - 50) / 50;
        return Math.round(yearHours + (maxHours - yearHours) * ratio);
    } else {
        const minHours = 1;
        const maxHours = 8760;
        const logMin = Math.log10(minHours);
        const logMax = Math.log10(maxHours);
        const ratio = (sliderValue - 1) / 49;
        const logValue = logMin + (logMax - logMin) * ratio;
        return Math.max(1, Math.round(Math.pow(10, logValue)));
    }
}

// Convert hours to display string
export function hoursToDisplayString(hours) {
    if (hours >= 10000) return "All Data";
    if (hours >= 8760) return "~1 year";
    if (hours >= 720) return `~${Math.round(hours / 720 * 10) / 10} months`;
    if (hours >= 168) return `~${Math.round(hours / 168 * 10) / 10} weeks`;
    if (hours >= 24) return `~${Math.round(hours / 24 * 10) / 10} days`;
    return `${hours} hours`;
}

// Generate time labels
export function generateTimeLabels(dataPointCount, totalHours) {
    const labels = [];
    const now = new Date();
    const intervalMs = (totalHours * 60 * 60 * 1000) / (dataPointCount - 1);

    for (let i = 0; i < dataPointCount; i++) {
        const timeMs = now.getTime() - (totalHours * 60 * 60 * 1000) + (i * intervalMs);
        const date = new Date(timeMs);

        if (totalHours >= 720) {
            labels.push(date.toLocaleDateString());
        } else if (totalHours >= 48) {
            labels.push(`${date.toLocaleDateString()} ${date.getHours()}:00`);
        } else if (totalHours >= 24) {
            labels.push(`${date.toLocaleDateString().split('/')[1]}/${date.toLocaleDateString().split('/')[0]} ${date.getHours()}:00`);
        } else {
            labels.push(date.toLocaleTimeString());
        }
    }

    return labels;
}

// Interpolate data points
export function interpolateDataPoints(originalData, originalLabels, targetCount, totalHours) {
    if (originalData.length === 0) {
        return { data: new Array(targetCount).fill(0), labels: generateTimeLabels(targetCount, totalHours) };
    }

    if (originalData.length >= targetCount) {
        const step = Math.floor(originalData.length / targetCount);
        const sampledData = [];
        const sampledLabels = [];

        for (let i = 0; i < targetCount; i++) {
            const index = Math.min(i * step, originalData.length - 1);
            sampledData.push(originalData[index]);
            if (originalLabels && originalLabels[index]) {
                sampledLabels.push(originalLabels[index]);
            }
        }

        return { data: sampledData, labels: sampledLabels.length > 0 ? sampledLabels : generateTimeLabels(targetCount, totalHours) };
    }

    const interpolatedData = [];
    const ratio = (originalData.length - 1) / (targetCount - 1);

    for (let i = 0; i < targetCount; i++) {
        const originalIndex = i * ratio;
        const lowerIndex = Math.floor(originalIndex);
        const upperIndex = Math.ceil(originalIndex);

        if (lowerIndex === upperIndex) {
            interpolatedData.push(originalData[lowerIndex]);
        } else {
            const fraction = originalIndex - lowerIndex;
            const interpolatedValue = originalData[lowerIndex] * (1 - fraction) + originalData[upperIndex] * fraction;
            interpolatedData.push(interpolatedValue);
        }
    }

    return { data: interpolatedData, labels: generateTimeLabels(targetCount, totalHours) };
}

// Get device locations
export async function getDeviceLocations() {
    try {
        const response = await fetch('/api/devices');
        const devices = await response.json();
        const locations = {};
        Object.entries(devices).forEach(([deviceId, data]) => {
            locations[deviceId] = data.latest_data?.location || deviceId;
        });
        return locations;
    } catch (error) {
        console.error('Error fetching device locations:', error);
    }
    return {};
}
