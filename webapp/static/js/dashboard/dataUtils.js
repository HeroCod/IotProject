/**
 * Data Utilities
 *
 * Functions for data transformation, interpolation, and time label generation.
 */

// Convert slider value to minutes using logarithmic scale
export function sliderToMinutes(sliderValue) {
    const minMinutes = 3;
    const maxMinutes = 4320; // 72 hours
    if (sliderValue <= 1) return minMinutes;
    if (sliderValue >= 100) return maxMinutes;

    // Logarithmic mapping
    const logMin = Math.log(minMinutes);
    const logMax = Math.log(maxMinutes);
    const scale = (logMax - logMin) / 99; // 100 - 1 = 99 steps

    const logValue = logMin + (sliderValue - 1) * scale;
    return Math.round(Math.exp(logValue));
}

// Convert minutes to display string
export function minutesToDisplayString(minutes) {
    if (minutes < 60) {
        return `${minutes} min`;
    } else if (minutes < 1440) { // less than 24 hours
        const hours = Math.round(minutes / 60 * 10) / 10;
        return `~${hours} hours`;
    } else {
        const days = Math.round(minutes / 1440 * 10) / 10;
        return `~${days} days`;
    }
}

// Generate time labels for interpolated data
export function generateTimeLabels(dataPointCount, totalMinutes) {
    const labels = [];
    const intervalMinutes = totalMinutes / (dataPointCount - 1);

    for (let i = 0; i < dataPointCount; i++) {
        const minutesAgo = totalMinutes - (i * intervalMinutes);
        const time = new Date(Date.now() - minutesAgo * 60 * 1000);
        labels.push(time.toLocaleTimeString());
    }

    return labels;
}

// Interpolate data points with proper gap handling
// dataWithTimestamps: array of {timestamp: Date, value: number|null}
export function interpolateDataPointsWithGaps(dataWithTimestamps, targetCount, totalMinutes) {
    const interpolatedData = [];
    const interpolatedLabels = [];
    const maxGapMinutes = 5; // If data gap is more than 5 minutes, show null (gap in graph)

    if (dataWithTimestamps.length === 0) {
        console.log('⚠️ No data points to interpolate');
        // Fallback to current time if no data
        const fallbackLabels = generateTimeLabels(targetCount, totalMinutes);
        return { data: new Array(targetCount).fill(null), labels: fallbackLabels };
    }

    // Use the LATEST data point timestamp as the reference "now"
    // This ensures we align with actual data instead of current browser time
    const latestDataTime = dataWithTimestamps[dataWithTimestamps.length - 1].timestamp.getTime();
    const earliestDataTime = dataWithTimestamps[0].timestamp.getTime();
    const dataSpanMinutes = (latestDataTime - earliestDataTime) / (60 * 1000);

    console.log(`📊 Interpolating ${dataWithTimestamps.length} points to ${targetCount} points over ${totalMinutes} minutes`);
    console.log(`📊 Data time range (Local): ${dataWithTimestamps[0].timestamp.toLocaleString()} to ${dataWithTimestamps[dataWithTimestamps.length-1].timestamp.toLocaleString()}`);
    console.log(`📊 Data span: ${dataSpanMinutes.toFixed(1)} minutes`);
    console.log(`📊 Target window (Local): from ${new Date(latestDataTime - totalMinutes * 60 * 1000).toLocaleString()} to ${new Date(latestDataTime).toLocaleString()}`);

    // For each target point in our output, calculate based on LATEST data time
    for (let i = 0; i < targetCount; i++) {
        const minutesAgo = totalMinutes - (i * (totalMinutes / (targetCount - 1)));
        const targetTime = new Date(latestDataTime - minutesAgo * 60 * 1000);

        // Find the closest data points before and after target time
        let beforePoint = null;
        let afterPoint = null;

        for (let j = 0; j < dataWithTimestamps.length; j++) {
            const point = dataWithTimestamps[j];
            if (point.timestamp <= targetTime) {
                if (!beforePoint || point.timestamp > beforePoint.timestamp) {
                    beforePoint = point;
                }
            }
            if (point.timestamp >= targetTime) {
                if (!afterPoint || point.timestamp < afterPoint.timestamp) {
                    afterPoint = point;
                }
            }
        }

        // Determine value for this target point
        let value = null;

        if (beforePoint && afterPoint) {
            // We have data on both sides
            const timeDiff = (afterPoint.timestamp - beforePoint.timestamp) / (60 * 1000); // in minutes

            if (timeDiff > maxGapMinutes) {
                // Gap too large, return null to show gap in graph
                value = null;
            } else if (beforePoint.value === null && afterPoint.value === null) {
                // Both null, keep null
                value = null;
            } else if (beforePoint.value === null) {
                // Only after has value, use it if close enough
                const afterDiff = (afterPoint.timestamp - targetTime) / (60 * 1000);
                value = afterDiff <= maxGapMinutes ? afterPoint.value : null;
            } else if (afterPoint.value === null) {
                // Only before has value, use it if close enough
                const beforeDiff = (targetTime - beforePoint.timestamp) / (60 * 1000);
                value = beforeDiff <= maxGapMinutes ? beforePoint.value : null;
            } else {
                // Both have values, interpolate
                const ratio = (targetTime - beforePoint.timestamp) / (afterPoint.timestamp - beforePoint.timestamp);
                value = beforePoint.value + (afterPoint.value - beforePoint.value) * ratio;
            }
        } else if (beforePoint) {
            // Only have data before target time
            const timeDiff = (targetTime - beforePoint.timestamp) / (60 * 1000);
            value = (timeDiff <= maxGapMinutes && beforePoint.value !== null) ? beforePoint.value : null;
        } else if (afterPoint) {
            // Only have data after target time
            const timeDiff = (afterPoint.timestamp - targetTime) / (60 * 1000);
            value = (timeDiff <= maxGapMinutes && afterPoint.value !== null) ? afterPoint.value : null;
        }
        // else: no data at all, value stays null

        interpolatedData.push(value);
        // Generate label based on targetTime (which is aligned with actual data)
        interpolatedLabels.push(targetTime.toLocaleTimeString());
    }

    return { data: interpolatedData, labels: interpolatedLabels };
}

// Helper function to shift color hue
export function shiftColorHue(hex, degrees) {
    // Convert hex to RGB
    const r = parseInt(hex.slice(1, 3), 16) / 255;
    const g = parseInt(hex.slice(3, 5), 16) / 255;
    const b = parseInt(hex.slice(5, 7), 16) / 255;

    // Convert RGB to HSL
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    let h, s, l = (max + min) / 2;

    if (max === min) {
        h = s = 0;
    } else {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        switch (max) {
            case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
            case g: h = ((b - r) / d + 2) / 6; break;
            case b: h = ((r - g) / d + 4) / 6; break;
        }
    }

    // Shift hue
    h = (h * 360 + degrees) % 360 / 360;

    // Convert HSL back to RGB
    let r2, g2, b2;
    if (s === 0) {
        r2 = g2 = b2 = l;
    } else {
        const hue2rgb = (p, q, t) => {
            if (t < 0) t += 1;
            if (t > 1) t -= 1;
            if (t < 1/6) return p + (q - p) * 6 * t;
            if (t < 1/2) return q;
            if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
            return p;
        };
        const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
        const p = 2 * l - q;
        r2 = hue2rgb(p, q, h + 1/3);
        g2 = hue2rgb(p, q, h);
        b2 = hue2rgb(p, q, h - 1/3);
    }

    // Convert back to hex
    const toHex = (x) => {
        const hex = Math.round(x * 255).toString(16);
        return hex.length === 1 ? '0' + hex : hex;
    };

    return `#${toHex(r2)}${toHex(g2)}${toHex(b2)}`;
}

// Helper function to convert hex to rgba
export function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
