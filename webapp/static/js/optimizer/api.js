/**
 * Optimizer API Functions
 */

export function loadOptimizerStatus() {
    return fetch('/api/model-info')
        .then(response => response.json())
        .then(data => {
            updateModelStatus(data);
            return data;
        })
        .catch(error => {
            console.error('Error loading optimizer status:', error);
            throw error;
        });
}

export function refreshOptimizer() {
    return fetch('/api/system/refresh', { method: 'POST' })
        .then(response => response.json());
}

export function enableOptimizer() {
    return fetch('/api/devices/all/override/clear', { method: 'POST' })
        .then(response => response.json());
}

function updateModelStatus(data) {
    const modelStatus = document.getElementById('model-status');
    if (modelStatus) {
        modelStatus.textContent = data.model_loaded ? 'Active' : 'Inactive';
        modelStatus.className = `status-value ${data.model_loaded ? 'status-online' : 'status-offline'}`;
    }

    const decisionsCount = document.getElementById('decisions-count');
    if (decisionsCount) decisionsCount.textContent = data.total_decisions || 0;

    const energySaved = document.getElementById('energy-saved');
    if (energySaved) energySaved.textContent = (data.energy_saved || 0).toFixed(3);

    const mlOptimizations = document.getElementById('ml-optimizations');
    if (mlOptimizations) mlOptimizations.textContent = data.ml_optimizations || 0;

    const modelInfo = document.getElementById('model-info');
    if (modelInfo) {
        modelInfo.innerHTML = `
            <p><strong>Model Type:</strong> ${data.model_type || 'N/A'}</p>
            <p><strong>Decision Method:</strong> ${data.decision_method || 'N/A'}</p>
            <p><strong>Features Available:</strong> ${data.features_available ? 'Yes' : 'No'}</p>
            <p><strong>Feature Count:</strong> ${data.feature_count || 0}</p>
            <p><strong>Accuracy:</strong> ${data.accuracy || 'N/A'}</p>
            <p><strong>Energy Efficiency:</strong> ${data.energy_efficiency || 'N/A'}</p>
        `;
    }
}
