/**
 * Insights Module
 *
 * Generates AI-driven insights from historical data.
 */

/**
 * Generate insights from historical data
 */
export function generateInsights(historicalData) {
    const container = document.getElementById('insights-container');
    const insights = [];

    // Calculate basic statistics
    const totalConsumption = historicalData.reduce((sum, d) =>
        sum + (d.data.room_usage || 0), 0);
    const avgConsumption = totalConsumption / Math.max(historicalData.length, 1);

    // Energy waste detection
    const wasteEvents = historicalData.filter(d =>
        d.data.occupancy === 0 && (d.data.room_usage || 0) > 0.05);

    if (wasteEvents.length > 0) {
        insights.push({
            icon: '⚠️',
            title: 'Energy Waste Detected',
            description: `Found ${wasteEvents.length} instances where lights were on in unoccupied rooms. Potential savings: ${(wasteEvents.length * 0.05).toFixed(3)} kWh`
        });
    }

    // Optimization events
    const optimizationEvents = historicalData.filter(d =>
        d.data.optimization_event === 1);

    if (optimizationEvents.length > 0) {
        insights.push({
            icon: '⚡',
            title: 'Optimization Events',
            description: `Detected ${optimizationEvents.length} instances where lights were on with no occupancy for 3+ consecutive readings. Potential energy savings identified.`
        });
    }

    // Manual overrides analysis
    const manualEvents = historicalData.filter(d =>
        d.data.manual_override === 1);

    if (manualEvents.length > 0) {
        insights.push({
            icon: '🔧',
            title: 'Manual Control Usage',
            description: `Users manually controlled lights ${manualEvents.length} times. Consider reviewing user preferences for better automation`
        });
    }

    // Ambient light optimization
    const ambientOptimizations = historicalData.filter(d =>
        (d.data.lux || 0) >= 65 && d.data.led_status === 0);

    if (ambientOptimizations.length > 0) {
        insights.push({
            icon: '☀️',
            title: 'Ambient Light Optimization',
            description: `Ambient light prevented unnecessary lighting ${ambientOptimizations.length} times when natural light was sufficient`
        });
    }

    // Peak usage analysis
    const highConsumption = historicalData.filter(d =>
        (d.data.room_usage || 0) > avgConsumption * 1.5);

    if (highConsumption.length > 0) {
        insights.push({
            icon: '📊',
            title: 'Peak Usage Analysis',
            description: `${highConsumption.length} high consumption events detected. Average usage: ${avgConsumption.toFixed(3)} kWh`
        });
    }

    // Default insight if no specific patterns found
    if (insights.length === 0) {
        insights.push({
            icon: '✅',
            title: 'System Operating Normally',
            description: 'No significant energy waste patterns detected. The ML optimization system is working efficiently.'
        });
    }

    // Render insights
    container.innerHTML = insights.map(insight => `
        <div class="insight-item">
            <div class="insight-icon">${insight.icon}</div>
            <div class="insight-text">
                <div class="insight-title">${insight.title}</div>
                <div class="insight-description">${insight.description}</div>
            </div>
        </div>
    `).join('');
}
