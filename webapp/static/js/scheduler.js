/**
 * Temperature Schedule Manager
 *
 * Interactive schedule editor for smart heating system
 */

// Global state
let currentSchedule = Array(168).fill(0); // 7 days * 24 hours (0 = unset)
let currentDay = 0;
let selectedHours = new Set();
let copiedDay = null;
let selectedDevice = null;
let savedSchedules = [];
let weekOverviewChart = null;

/**
 * Update system status indicators
 */
function updateStatus(status) {
    const mqttStatus = document.getElementById('mqtt-status');
    const dbStatus = document.getElementById('db-status');
    const aiStatus = document.getElementById('ai-status');
    const mqttText = document.getElementById('mqtt-text');
    const dbText = document.getElementById('db-text');
    const aiText = document.getElementById('ai-text');
    const nodesCount = document.getElementById('nodes-count');

    if (mqttStatus && mqttText) {
        mqttStatus.className = `status-indicator ${status.system_status.mqtt_connected ? 'status-online' : 'status-offline'}`;
        mqttText.textContent = status.system_status.mqtt_connected ? 'Connected' : 'Disconnected';
    }

    if (dbStatus && dbText) {
        dbStatus.className = `status-indicator ${status.system_status.db_connected ? 'status-online' : 'status-offline'}`;
        dbText.textContent = status.system_status.db_connected ? 'Connected' : 'Disconnected';
    }

    // Update heating system status
    const heatingActive = Object.values(status.latest_data || {}).some(device =>
        device.data && device.data.heating_status === 1
    );
    if (aiStatus && aiText) {
        aiStatus.className = `status-indicator ${heatingActive ? 'status-online' : 'status-offline'}`;
        aiText.textContent = heatingActive ? 'Active' : 'Standby';
    }

    if (nodesCount) {
        nodesCount.textContent = status.system_status.nodes_online || 0;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('📅 Initializing Temperature Schedule Manager...');

    initializeHourGrid();
    loadSavedSchedules();
    loadDevices();
    initializeWeekOverview();
    switchDay();

    // Fetch initial status
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            console.log('📊 Initial status received:', data);
            updateStatus(data);
        })
        .catch(error => console.error('❌ Error fetching initial status:', error));

    // Set up periodic status updates
    setInterval(() => {
        fetch('/api/status')
            .then(response => response.json())
            .then(data => {
                updateStatus(data);
            })
            .catch(error => console.error('❌ Error in status update:', error));
    }, 5000);
});

// Initialize hour grid for current day
function initializeHourGrid() {
    const grid = document.getElementById('hour-grid');
    grid.innerHTML = '';

    for (let hour = 0; hour < 24; hour++) {
        const cell = document.createElement('div');
        cell.className = 'hour-cell';
        cell.dataset.hour = hour;

        const label = document.createElement('div');
        label.className = 'hour-label';
        label.textContent = `${hour.toString().padStart(2, '0')}:00`;

        const temp = document.createElement('div');
        temp.className = 'hour-temp';
        temp.textContent = '--';

        cell.appendChild(label);
        cell.appendChild(temp);

        // Click to select
        cell.addEventListener('click', function(e) {
            if (e.ctrlKey || e.metaKey) {
                // Multi-select with Ctrl/Cmd
                toggleHourSelection(hour);
            } else if (e.shiftKey && selectedHours.size > 0) {
                // Range select with Shift
                selectHourRange(hour);
            } else {
                // Single select
                clearSelection();
                toggleHourSelection(hour);
            }
        });

        grid.appendChild(cell);
    }
}

// Switch to different day
function switchDay() {
    const selector = document.getElementById('day-selector');
    currentDay = parseInt(selector.value);
    clearSelection();
    updateHourGrid();
    console.log(`📅 Switched to day ${currentDay}`);
}

// Update hour grid display
function updateHourGrid() {
    const cells = document.querySelectorAll('.hour-cell');
    cells.forEach((cell, hour) => {
        const scheduleIndex = currentDay * 24 + hour;
        const temp = currentSchedule[scheduleIndex];
        const tempDisplay = cell.querySelector('.hour-temp');

        if (temp === 0 || temp === null) {
            tempDisplay.textContent = '--';
            tempDisplay.className = 'hour-temp unset';
            cell.classList.add('unset');
        } else {
            tempDisplay.textContent = `${temp}°`;
            tempDisplay.className = 'hour-temp';
            cell.classList.remove('unset');

            // Color coding
            if (temp < 18) {
                tempDisplay.classList.add('cold');
            } else if (temp > 22) {
                tempDisplay.classList.add('warm');
            }
        }
    });
}

// Toggle hour selection
function toggleHourSelection(hour) {
    const cell = document.querySelector(`.hour-cell[data-hour="${hour}"]`);
    if (selectedHours.has(hour)) {
        selectedHours.delete(hour);
        cell.classList.remove('selected');
    } else {
        selectedHours.add(hour);
        cell.classList.add('selected');
    }
}

// Select range of hours
function selectHourRange(endHour) {
    const startHour = Math.min(...Array.from(selectedHours));
    const start = Math.min(startHour, endHour);
    const end = Math.max(startHour, endHour);

    for (let hour = start; hour <= end; hour++) {
        selectedHours.add(hour);
        const cell = document.querySelector(`.hour-cell[data-hour="${hour}"]`);
        cell.classList.add('selected');
    }
}

// Clear selection
function clearSelection() {
    selectedHours.clear();
    document.querySelectorAll('.hour-cell.selected').forEach(cell => {
        cell.classList.remove('selected');
    });
}

// Apply temperature to selected hours
function applyTempToSelected() {
    if (selectedHours.size === 0) {
        showMessage('Please select hours first', 'warning');
        return;
    }

    const tempInput = document.getElementById('temp-input');
    const temp = parseFloat(tempInput.value);

    if (temp < 10 || temp > 30) {
        showMessage('Temperature must be between 10°C and 30°C', 'error');
        return;
    }

    selectedHours.forEach(hour => {
        const scheduleIndex = currentDay * 24 + hour;
        currentSchedule[scheduleIndex] = temp;
    });

    updateHourGrid();
    updateWeekOverview();
    clearSelection();
    showMessage(`✓ Applied ${temp}°C to ${selectedHours.size} hour(s)`, 'success');
}

// Copy current day
function copyDay() {
    const startIndex = currentDay * 24;
    copiedDay = currentSchedule.slice(startIndex, startIndex + 24);
    showMessage('📋 Day copied to clipboard', 'success');
}

// Paste to current day
function pasteDay() {
    if (!copiedDay) {
        showMessage('No day copied', 'warning');
        return;
    }

    const startIndex = currentDay * 24;
    for (let i = 0; i < 24; i++) {
        currentSchedule[startIndex + i] = copiedDay[i];
    }

    updateHourGrid();
    updateWeekOverview();
    showMessage('📄 Day pasted', 'success');
}

// Fill entire day with temperature
function fillDay() {
    const tempInput = document.getElementById('temp-input');
    const temp = parseFloat(tempInput.value);

    if (temp < 10 || temp > 30) {
        showMessage('Temperature must be between 10°C and 30°C', 'error');
        return;
    }

    const startIndex = currentDay * 24;
    for (let i = 0; i < 24; i++) {
        currentSchedule[startIndex + i] = temp;
    }

    updateHourGrid();
    updateWeekOverview();
    showMessage(`🔢 Filled day with ${temp}°C`, 'success');
}

// Copy to all weekdays (Mon-Fri)
function copyWeekday() {
    const startIndex = currentDay * 24;
    copiedDay = currentSchedule.slice(startIndex, startIndex + 24);

    for (let day = 0; day < 5; day++) {
        for (let hour = 0; hour < 24; hour++) {
            currentSchedule[day * 24 + hour] = copiedDay[hour];
        }
    }

    updateHourGrid();
    updateWeekOverview();
    showMessage('📅 Copied to all weekdays (Mon-Fri)', 'success');
}

// Copy to weekend (Sat-Sun)
function copyWeekend() {
    const startIndex = currentDay * 24;
    copiedDay = currentSchedule.slice(startIndex, startIndex + 24);

    for (let day = 5; day < 7; day++) {
        for (let hour = 0; hour < 24; hour++) {
            currentSchedule[day * 24 + hour] = copiedDay[hour];
        }
    }

    updateHourGrid();
    updateWeekOverview();
    showMessage('🏖️ Copied to weekend (Sat-Sun)', 'success');
}

// Reset schedule
function resetSchedule() {
    if (!confirm('Are you sure you want to reset the entire schedule?')) {
        return;
    }

    currentSchedule = Array(168).fill(0);
    updateHourGrid();
    updateWeekOverview();
    document.getElementById('schedule-name').value = '';
    document.getElementById('schedule-description').value = '';
    showMessage('🔄 Schedule reset', 'info');
}

// Load preset schedule
function loadPreset(presetName) {
    fetch(`/api/presets/schedule/${presetName}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                currentSchedule = data.schedule;
                document.getElementById('schedule-name').value = data.name;
                document.getElementById('schedule-description').value = data.description;
                updateHourGrid();
                updateWeekOverview();
                showMessage(`✓ Loaded preset: ${data.name}`, 'success');
            } else {
                showMessage(`Error: ${data.error}`, 'error');
            }
        })
        .catch(error => {
            console.error('Error loading preset:', error);
            showMessage('Failed to load preset', 'error');
        });
}

// Save schedule to database
function saveSchedule() {
    const name = document.getElementById('schedule-name').value.trim();
    const description = document.getElementById('schedule-description').value.trim();

    if (!name) {
        showMessage('Please enter a schedule name', 'warning');
        return;
    }

    fetch('/api/schedules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name: name,
            description: description,
            schedule: currentSchedule
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showMessage(`💾 Schedule "${name}" saved successfully`, 'success');
            loadSavedSchedules();
        } else {
            showMessage(`Error: ${data.error}`, 'error');
        }
    })
    .catch(error => {
        console.error('Error saving schedule:', error);
        showMessage('Failed to save schedule', 'error');
    });
}

// Load schedule from database
function loadSchedule() {
    const selected = document.querySelector('.schedule-item.selected');
    if (!selected) {
        showMessage('Please select a saved schedule first', 'warning');
        return;
    }

    const scheduleId = selected.dataset.id;

    fetch(`/api/schedules/${scheduleId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                currentSchedule = data.schedule.schedule_data;
                document.getElementById('schedule-name').value = data.schedule.name;
                document.getElementById('schedule-description').value = data.schedule.description;
                updateHourGrid();
                updateWeekOverview();
                showMessage(`📂 Loaded schedule: ${data.schedule.name}`, 'success');
            } else {
                showMessage(`Error: ${data.error}`, 'error');
            }
        })
        .catch(error => {
            console.error('Error loading schedule:', error);
            showMessage('Failed to load schedule', 'error');
        });
}

// Load saved schedules from database
function loadSavedSchedules() {
    fetch('/api/schedules')
        .then(response => response.json())
        .then(data => {
            savedSchedules = data.schedules || [];
            displaySavedSchedules();
        })
        .catch(error => {
            console.error('Error loading schedules:', error);
            document.getElementById('saved-schedules-list').innerHTML =
                '<p class="loading">Failed to load schedules</p>';
        });
}

// Display saved schedules
function displaySavedSchedules() {
    const container = document.getElementById('saved-schedules-list');

    if (savedSchedules.length === 0) {
        container.innerHTML = '<p class="loading">No saved schedules yet</p>';
        return;
    }

    container.innerHTML = '';
    savedSchedules.forEach(schedule => {
        const item = document.createElement('div');
        item.className = 'schedule-item';
        item.dataset.id = schedule.id;

        item.innerHTML = `
            <div class="schedule-item-name">${schedule.name}</div>
            <div class="schedule-item-desc">${schedule.description || 'No description'}</div>
            <div class="schedule-item-meta">
                <span>Created: ${new Date(schedule.created_at).toLocaleDateString()}</span>
            </div>
            <div class="schedule-item-actions">
                <button class="btn btn-sm" onclick="loadScheduleById(${schedule.id})">📂 Load</button>
                <button class="btn btn-sm btn-danger" onclick="deleteSchedule(${schedule.id})">🗑️ Delete</button>
            </div>
        `;

        item.addEventListener('click', function(e) {
            if (!e.target.closest('button')) {
                document.querySelectorAll('.schedule-item').forEach(i => i.classList.remove('selected'));
                item.classList.add('selected');
            }
        });

        container.appendChild(item);
    });
}

// Load schedule by ID
function loadScheduleById(id) {
    fetch(`/api/schedules/${id}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                currentSchedule = data.schedule.schedule_data;
                document.getElementById('schedule-name').value = data.schedule.name;
                document.getElementById('schedule-description').value = data.schedule.description;
                updateHourGrid();
                updateWeekOverview();
                showMessage(`📂 Loaded: ${data.schedule.name}`, 'success');
            } else {
                showMessage(`Error: ${data.error}`, 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showMessage('Failed to load schedule', 'error');
        });
}

// Delete schedule
function deleteSchedule(id) {
    const schedule = savedSchedules.find(s => s.id === id);
    if (!confirm(`Delete schedule "${schedule.name}"?`)) {
        return;
    }

    fetch(`/api/schedules/${id}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showMessage('🗑️ Schedule deleted', 'success');
                loadSavedSchedules();
            } else {
                showMessage(`Error: ${data.error}`, 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showMessage('Failed to delete schedule', 'error');
        });
}

// Load devices
function loadDevices() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            displayDevices(data.latest_data || {});
        })
        .catch(error => {
            console.error('Error loading devices:', error);
            document.getElementById('device-list').innerHTML =
                '<p class="loading">Failed to load devices</p>';
        });
}

// Display devices
function displayDevices(devices) {
    const container = document.getElementById('device-list');

    if (Object.keys(devices).length === 0) {
        container.innerHTML = '<p class="loading">No devices online</p>';
        return;
    }

    container.innerHTML = '';
    Object.entries(devices).forEach(([deviceId, deviceData]) => {
        const card = document.createElement('div');
        card.className = 'device-card';
        card.dataset.deviceId = deviceId;

        const location = deviceData.data?.location || 'Unknown';

        card.innerHTML = `
            <div class="device-card-name">${deviceId}</div>
            <div class="device-card-location">📍 ${location}</div>
        `;

        card.addEventListener('click', function() {
            document.querySelectorAll('.device-card').forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            selectedDevice = deviceId;
        });

        container.appendChild(card);
    });
}

// Apply schedule to selected device
function applyToDevice() {
    if (!selectedDevice) {
        showMessage('Please select a device first', 'warning');
        return;
    }

    if (!confirm(`Apply schedule to ${selectedDevice}?`)) {
        return;
    }

    fetch(`/api/schedule/${selectedDevice}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ schedule: currentSchedule })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showMessage(`✓ Schedule applied to ${selectedDevice}`, 'success');
        } else {
            showMessage(`Error: ${data.error}`, 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showMessage('Failed to apply schedule', 'error');
    });
}

// Apply schedule to all devices
function applyToAllDevices() {
    if (!confirm('Apply schedule to ALL devices?')) {
        return;
    }

    const devices = document.querySelectorAll('.device-card');
    let completed = 0;
    let errors = 0;

    devices.forEach(card => {
        const deviceId = card.dataset.deviceId;

        fetch(`/api/schedule/${deviceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ schedule: currentSchedule })
        })
        .then(response => response.json())
        .then(data => {
            completed++;
            if (!data.success) errors++;

            if (completed === devices.length) {
                if (errors === 0) {
                    showMessage(`✓ Schedule applied to all ${devices.length} devices`, 'success');
                } else {
                    showMessage(`Applied to ${completed - errors}/${devices.length} devices (${errors} errors)`, 'warning');
                }
            }
        })
        .catch(error => {
            completed++;
            errors++;
            console.error(`Error applying to ${deviceId}:`, error);
        });
    });
}

// Initialize week overview chart
function initializeWeekOverview() {
    const ctx = document.getElementById('weekOverviewChart').getContext('2d');
    weekOverviewChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Temperature Schedule',
                data: [],
                borderColor: '#ffa500',
                backgroundColor: '#ffa50040',
                tension: 0.1,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true },
                tooltip: {
                    callbacks: {
                        title: function(context) {
                            return context[0].label;
                        },
                        label: function(context) {
                            const temp = context.parsed.y;
                            return temp === 0 ? 'Unset' : `${temp}°C`;
                        }
                    }
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
                    }
                }
            }
        }
    });

    updateWeekOverview();
}

// Update week overview chart
function updateWeekOverview() {
    if (!weekOverviewChart) return;

    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const labels = [];
    const data = [];

    for (let day = 0; day < 7; day++) {
        for (let hour = 0; hour < 24; hour++) {
            if (hour % 6 === 0) { // Show label every 6 hours
                labels.push(`${days[day]} ${hour}:00`);
            } else {
                labels.push('');
            }

            const temp = currentSchedule[day * 24 + hour];
            data.push(temp === 0 ? null : temp);
        }
    }

    weekOverviewChart.data.labels = labels;
    weekOverviewChart.data.datasets[0].data = data;
    weekOverviewChart.update();
}

// Show message
function showMessage(message, type) {
    const msgEl = document.getElementById('response-message');
    msgEl.textContent = message;
    msgEl.className = `response-message ${type}`;
    msgEl.style.display = 'block';

    setTimeout(() => {
        msgEl.style.display = 'none';
    }, 5000);
}
