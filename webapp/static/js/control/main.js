/**
 * Control Page Main
 *
 * Coordinates device control functionality
 */

import { sendCommand, removeOverride, saveDuration, globalCommand, enableEnergyMode, getDurationValue } from './controls.js';
import { refreshDevices } from './deviceCards.js';
import { initializeSocketHandlers } from './socketHandlers.js';

// Socket.IO connection
const socket = io();

// Make functions globally available for HTML onclick
window.sendCommand = sendCommand;
window.removeOverride = removeOverride;
window.saveDuration = saveDuration;
window.getDurationValue = getDurationValue;
window.globalCommand = globalCommand;
window.enableEnergyMode = enableEnergyMode;
window.refreshDevices = refreshDevices;

// Initialize Socket.IO handlers
initializeSocketHandlers(socket);

// Initialize page on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('🎛️ Control page initialized');
    refreshDevices();
});
