// Variables
let autoScroll = true;
let eventSource;
let startTime = new Date();
let consoleElement;
let connectionStatus;

// System state
let systemState = {
    door_state: false,
    light_state: false,
    user_present: false,
    luminosity: 0,
    last_update: null,
    detected_user: null,
    users_in_room: [],
    arduino_connected: false,
    manual_override: false  // Added manual override state
};

// Store user information
let users = {};

// Update system state and UI
function updateSystemState(newState) {
    // Update our local state
    Object.assign(systemState, newState);
    
    // Update UI elements
    updateLightStatus();
    updateDoorStatus();
    updatePresenceStatus();
    updateLuminosityStatus();
    updateUsersInRoom();
    updateArduinoStatus();
    updateOverrideStatus(); // Added to update override status
    
    // Update last update time
    if (newState.last_update) {
        document.getElementById('last-update').textContent = 'Just now';
    }
}

// Update light status indicator
function updateLightStatus() {
    const lightStatus = document.getElementById('light-status');
    const lightIcon = document.getElementById('light-icon');
    
    if (systemState.light_state) {
        lightStatus.textContent = 'ON';
        lightStatus.className = 'status-value status-on';
        lightIcon.textContent = '💡';
    } else {
        lightStatus.textContent = 'OFF';
        lightStatus.className = 'status-value status-off';
        lightIcon.textContent = '🔅';
    }
}

// Update door status indicator
function updateDoorStatus() {
    const doorStatus = document.getElementById('door-status');
    const doorIcon = document.getElementById('door-icon');
    
    if (systemState.door_state) {
        doorStatus.textContent = 'OPEN';
        doorStatus.className = 'status-value status-active';
        doorIcon.textContent = '🚪↔️';
    } else {
        doorStatus.textContent = 'CLOSED';
        doorStatus.className = 'status-value status-inactive';
        doorIcon.textContent = '🚪';
    }
}

// Update presence status indicator
function updatePresenceStatus() {
    const presenceStatus = document.getElementById('presence-status');
    const presenceIcon = document.getElementById('presence-icon');
    
    if (systemState.user_present) {
        presenceStatus.textContent = 'DETECTED';
        presenceStatus.className = 'status-value status-active';
        presenceIcon.textContent = '👤✓';
    } else {
        presenceStatus.textContent = 'NONE';
        presenceStatus.className = 'status-value status-inactive';
        presenceIcon.textContent = '👤';
    }
}

// Update luminosity status indicator
function updateLuminosityStatus() {
    const luminosityValue = document.getElementById('luminosity-value');
    const luminosityIcon = document.getElementById('luminosity-icon');
    
    luminosityValue.textContent = systemState.luminosity;
    
    // Adjust icon based on luminosity level (threshold is arbitrary for visualization)
    if (systemState.luminosity > 700) {
        luminosityIcon.textContent = '☀️';
    } else if (systemState.luminosity > 300) {
        luminosityIcon.textContent = '🌤️';
    } else {
        luminosityIcon.textContent = '🌑';
    }
}

// Update manual override status indicator
function updateOverrideStatus() {
    const overrideStatus = document.getElementById('override-status');
    const overrideIcon = document.getElementById('override-icon');
    const overrideButton = document.getElementById('toggle-override');
    
    if (systemState.manual_override) {
        overrideStatus.textContent = 'ON';
        overrideStatus.className = 'status-value status-on';
        overrideIcon.textContent = '🔓';
        overrideButton.textContent = 'Disable Override';
    } else {
        overrideStatus.textContent = 'OFF';
        overrideStatus.className = 'status-value status-off';
        overrideIcon.textContent = '🔒';
        overrideButton.textContent = 'Enable Override';
    }
}

// Update users in room list
function updateUsersInRoom() {
    const usersList = document.getElementById('users-list');
    usersList.innerHTML = '';
    
    if (systemState.users_in_room && systemState.users_in_room.length > 0) {
        systemState.users_in_room.forEach(userId => {
            const userName = users[userId] ? users[userId].name : `User ${userId}`;
            
            const userElement = document.createElement('div');
            userElement.className = 'user-item';
            userElement.innerHTML = `
                <div class="user-icon">👤</div>
                <div class="user-name">${userName}</div>
            `;
            
            usersList.appendChild(userElement);
        });
    } else {
        const noUsersElement = document.createElement('div');
        noUsersElement.className = 'no-users';
        noUsersElement.textContent = 'No users detected';
        usersList.appendChild(noUsersElement);
    }
}

// Update Arduino connection status
function updateArduinoStatus() {
    const arduinoStatus = document.getElementById('arduino-status');
    
    if (systemState.arduino_connected) {
        arduinoStatus.textContent = 'Connected';
        arduinoStatus.className = 'stat-value status-on';
    } else {
        arduinoStatus.textContent = 'Disconnected';
        arduinoStatus.className = 'stat-value status-off';
    }
}

// Add log entry to console
function addLogEntry(data) {
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    
    // Create timestamp element
    const timestamp = document.createElement('span');
    timestamp.className = 'timestamp';
    timestamp.textContent = data.timestamp || new Date().toLocaleTimeString();
    
    // Create type/source element
    const type = document.createElement('span');
    type.className = `log-type log-type-${data.type || 'info'}`;
    type.textContent = data.type?.toUpperCase() || 'INFO';
    
    // Create message element
    const message = document.createElement('span');
    message.className = 'log-message';
    message.textContent = data.message || '';
    
    // Add the basic elements
    entry.appendChild(timestamp);
    entry.appendChild(type);
    entry.appendChild(message);
    
    // Add user if present (welcome messages)
    if (data.user) {
        const user = document.createElement('span');
        user.className = 'log-user';
        user.textContent = data.user;
        entry.appendChild(user);
    }
    
    // Add details if present
    if (data.details) {
        const details = document.createElement('div');
        details.className = 'log-details';
        details.textContent = JSON.stringify(data.details, null, 2);
        entry.appendChild(details);
    }
    
    consoleElement.appendChild(entry);
    
    // Auto-scroll to bottom if enabled
    if (autoScroll) {
        consoleElement.scrollTop = consoleElement.scrollHeight;
    }
    
    // Limit number of entries to prevent browser slowdown
    while (consoleElement.children.length > 100) {
        consoleElement.removeChild(consoleElement.firstChild);
    }
}

// Connect to server-sent events
function connectToEventSource() {
    if (eventSource) {
        eventSource.close();
    }
    
    eventSource = new EventSource('/events');
    
    eventSource.onopen = function() {
        console.log('Connection to server established.');
        connectionStatus.textContent = 'Connected';
        connectionStatus.classList.remove('disconnected');
        connectionStatus.classList.add('connected');
    };
    
    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            console.log('Event received:', data);
            
            // Process different event types
            if (data.type === 'initial_state' || data.type === 'update') {
                if (data.system_state) {
                    updateSystemState(data.system_state);
                }
                
                // Add to activity log
                if (data.type === 'update') {
                    addLogEntry({
                        type: 'update',
                        timestamp: data.timestamp,
                        message: 'System state updated',
                        details: data.data
                    });
                }
            } else if (data.type === 'welcome') {
                // Handle welcome message
                addLogEntry({
                    type: 'welcome',
                    timestamp: data.timestamp,
                    message: `Welcome ${data.user_name}!`,
                    user: data.user_name
                });
            } else if (data.type === 'override') {
                // Handle override toggle message
                addLogEntry({
                    type: 'control',
                    timestamp: data.timestamp,
                    message: `Manual override ${data.enabled ? 'enabled' : 'disabled'}`,
                    details: { enabled: data.enabled }
                });
                
                // Update system state
                systemState.manual_override = data.enabled;
                updateOverrideStatus();
            }
        } catch (e) {
            console.error('Error parsing event data:', e);
        }
    };
    
    eventSource.onerror = function(err) {
        console.log('EventSource connection error:', err);
        connectionStatus.textContent = 'Disconnected';
        connectionStatus.classList.remove('connected');
        connectionStatus.classList.add('disconnected');
        
        // Update Arduino status
        document.getElementById('arduino-status').textContent = 'Disconnected';
        document.getElementById('arduino-status').classList.add('error-state');
        
        // Reconnect after 5 seconds
        setTimeout(connectToEventSource, 5000);
    };
}

// Fetch users from server
function fetchUsers() {
    fetch('/api/users')
        .then(response => response.json())
        .then(data => {
            users = data;
            updateUsersInRoom();
        })
        .catch(error => console.error('Error fetching users:', error));
}

// Control light function
function controlLight(command) {
    fetch('/api/light/control', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
            command: command,
            override: systemState.manual_override  // Send current override state
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            addLogEntry({
                type: 'control',
                message: `Light turned ${command} successfully`
            });
            
            if (data.state) {
                updateSystemState(data.state);
            }
        } else {
            addLogEntry({
                type: 'error',
                message: `Failed to turn ${command} light: ${data.message}`
            });
        }
    })
    .catch(error => {
        console.error('Error controlling light:', error);
        addLogEntry({
            type: 'error',
            message: `Error controlling light: ${error.message}`
        });
    });
}

// Toggle manual override function
function toggleOverride() {
    const newState = !systemState.manual_override;
    
    fetch('/api/override', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ enable: newState })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            addLogEntry({
                type: 'control',
                message: `Manual override ${newState ? 'enabled' : 'disabled'}`
            });
            
            if (data.state) {
                updateSystemState(data.state);
            }
        } else {
            addLogEntry({
                type: 'error',
                message: `Failed to toggle override: ${data.message}`
            });
        }
    })
    .catch(error => {
        console.error('Error toggling override:', error);
        addLogEntry({
            type: 'error',
            message: `Error toggling override: ${error.message}`
        });
    });
}

// Update uptime every second
setInterval(() => {
    const now = new Date();
    const diffSeconds = Math.floor((now - startTime) / 1000);
    
    const days = Math.floor(diffSeconds / 86400);
    const hours = Math.floor((diffSeconds % 86400) / 3600);
    const minutes = Math.floor((diffSeconds % 3600) / 60);
    const seconds = diffSeconds % 60;
    
    let uptime = '';
    if (days > 0) uptime += `${days}d `;
    if (hours > 0 || days > 0) uptime += `${hours}h `;
    if (minutes > 0 || hours > 0 || days > 0) uptime += `${minutes}m `;
    uptime += `${seconds}s`;
    
    document.getElementById('system-uptime').textContent = uptime;
    
    // Update "last seen" time if we have a last update
    if (systemState.last_update) {
        const lastUpdate = new Date(systemState.last_update);
        const timeDiff = now - lastUpdate;
        const diffSeconds = Math.floor(timeDiff / 1000);
        
        let lastUpdateText;
        if (diffSeconds < 60) {
            lastUpdateText = `${diffSeconds}s ago`;
        } else if (diffSeconds < 3600) {
            lastUpdateText = `${Math.floor(diffSeconds / 60)}m ago`;
        } else if (diffSeconds < 86400) {
            lastUpdateText = `${Math.floor(diffSeconds / 3600)}h ago`;
        } else {
            lastUpdateText = `${Math.floor(diffSeconds / 86400)}d ago`;
        }
        
        document.getElementById('last-update').textContent = lastUpdateText;
    }
}, 1000);

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Get DOM elements
    consoleElement = document.getElementById('console');
    connectionStatus = document.getElementById('connection-status');
    
    // Add event listeners for buttons
    document.getElementById('clear-log').addEventListener('click', () => {
        consoleElement.innerHTML = '';
    });
    
    document.getElementById('auto-scroll').addEventListener('click', (e) => {
        autoScroll = !autoScroll;
        e.target.textContent = autoScroll ? 'Auto-scroll: ON' : 'Auto-scroll: OFF';
        e.target.classList.toggle('disabled', !autoScroll);
        
        if (autoScroll) {
            consoleElement.scrollTop = consoleElement.scrollHeight;
        }
    });
    
    // Light control buttons
    document.getElementById('light-on').addEventListener('click', () => {
        controlLight('on');
    });
    
    document.getElementById('light-off').addEventListener('click', () => {
        controlLight('off');
    });
    
    // Override toggle button
    document.getElementById('toggle-override').addEventListener('click', toggleOverride);
    
    // Initialize connection to server
    connectToEventSource();
    
    // Fetch users
    fetchUsers();
    
    // Add initial log entry
    addLogEntry({
        type: 'info',
        message: 'Smart Room Dashboard initialized'
    });
});
