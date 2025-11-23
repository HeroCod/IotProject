/**
 * Optimizer Page Main
 */

import { loadOptimizerStatus, refreshOptimizer as apiRefreshOptimizer, enableOptimizer as apiEnableOptimizer } from './api.js';
import { showMessage } from './ui.js';

// Make functions globally available
window.refreshOptimizer = function() {
    apiRefreshOptimizer()
        .then(data => {
            if (data.success) {
                showMessage('✅ System refreshed successfully', 'success');
                setTimeout(loadOptimizerStatus, 1000);
            } else {
                showMessage('❌ Refresh failed: ' + data.error, 'error');
            }
        })
        .catch(error => {
            showMessage('❌ Refresh error: ' + error.message, 'error');
        });
};

window.enableOptimizer = function() {
    apiEnableOptimizer()
        .then(data => {
            if (data.success) {
                showMessage('✅ Optimizer enabled - All overrides cleared', 'success');
                setTimeout(loadOptimizerStatus, 1000);
            } else {
                showMessage('❌ Enable failed: ' + data.error, 'error');
            }
        })
        .catch(error => {
            showMessage('❌ Enable error: ' + error.message, 'error');
        });
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('🤖 Optimizer page initialized');
    loadOptimizerStatus();
    setInterval(loadOptimizerStatus, 30000);
});
