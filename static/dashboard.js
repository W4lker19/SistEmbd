// Variables
let autoScroll = true;
let eventSource;
let startTime = new Date();
let consoleElement = document.getElementById('console');
let connectionStatus = document.getElementById('connection-status');

// Update uptime every second
setInterval(() => {
    const now = new Date();
    const diffSeconds = Math.floor((now - startTime) / 1000);
    let uptime = '';
    
    const days = Math.floor(diffSeconds / 86400);
    const hours = Math.floor((diffSeconds % 86400) / 3600);
    const minutes = Math.floor((diffSeconds % 3600) / 60);
    const seconds = diffSeconds % 60;
    
    if (days > 0) uptime += `${days}d `;
    if (hours > 0 || days > 0) uptime += `${hours}h `;
    if (minutes > 0 || hours > 0 || days > 0) uptime += `${minutes}m `;
    uptime += `${seconds}s`;
    
    document.getElementById('uptime').textContent = uptime;
}, 1000);

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
        console.log('Raw event received:', event.data); // Debug log
        try {
            const data = JSON.parse(event.data);
            console.log('Parsed event data:', data); // Debug log
            
            addLogEntry(data);
            
            // If it's a stats update, update the stats
            if (data.type === 'stats') {
                updateStats(data.stats);
            }
        } catch (e) {
            console.error('Error parsing event data:', e);
            console.error('Raw event data:', event.data);
        }
    };
    
    eventSource.onerror = function(err) {
        console.log('EventSource connection error:', err);
        connectionStatus.textContent = 'Disconnected';
        connectionStatus.classList.remove('connected');
        connectionStatus.classList.add('disconnected');
        
        // Reconnect after 5 seconds
        setTimeout(connectToEventSource, 5000);
    };
}

// Add log entry to console
function addLogEntry(data) {
    console.log('Adding log entry for:', data);
    
    // Skip stats updates for console display
    if (data.type === 'stats') return;
    
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    
    // Format based on message type
    if (data.type === 'message') {
        const timestamp = document.createElement('span');
        timestamp.className = 'timestamp';
        timestamp.textContent = data.timestamp;
        
        const source = document.createElement('span');
        source.className = 'source';
        source.textContent = data.data.source || 'unknown';
        
        const status = document.createElement('span');
        status.className = 'status';
        status.textContent = data.data.status || '';
        
        entry.appendChild(timestamp);
        entry.appendChild(source);
        entry.appendChild(status);
        
        // Add remaining data as JSON string
        const content = document.createElement('div');
        const dataToShow = {...data.data};
        // Remove items we've already displayed
        delete dataToShow.source;
        delete dataToShow.status;
        
        content.textContent = JSON.stringify(dataToShow, null, 2);
        entry.appendChild(content);
    } else {
        entry.textContent = typeof data === 'string' ? data : JSON.stringify(data);
    }
    
    consoleElement.appendChild(entry);
    
    // Auto-scroll to bottom if enabled
    if (autoScroll) {
        consoleElement.scrollTop = consoleElement.scrollHeight;
    }
    
    // Limit number of entries to prevent browser slowdown
    while (consoleElement.children.length > 500) {
        consoleElement.removeChild(consoleElement.firstChild);
    }
}

// Update statistics display
function updateStats(stats) {
    if (!stats) return;
    
    console.log('Updating stats:', stats);
    
    document.getElementById('total-messages').textContent = stats.total_messages || 0;
    document.getElementById('messages-today').textContent = stats.messages_today || 0;
    
    // Format last seen time nicely
    if (stats.last_seen) {
        const lastSeen = new Date(stats.last_seen);
        const now = new Date();
        const diffMs = now - lastSeen;
        const diffSeconds = Math.floor(diffMs / 1000);
        
        let lastSeenText;
        
        if (diffSeconds < 60) {
            lastSeenText = `${diffSeconds}s ago`;
        } else if (diffSeconds < 3600) {
            lastSeenText = `${Math.floor(diffSeconds / 60)}m ago`;
        } else if (diffSeconds < 86400) {
            lastSeenText = `${Math.floor(diffSeconds / 3600)}h ago`;
        } else {
            lastSeenText = `${Math.floor(diffSeconds / 86400)}d ago`;
        }
        
        document.getElementById('last-seen').textContent = lastSeenText;
    }
}

// Fetch initial stats
function fetchStats() {
    fetch('/stats')
        .then(response => response.json())
        .then(data => {
            console.log('Fetched stats:', data);
            if (data.uptime_stats) {
                updateStats({
                    total_messages: data.uptime_stats.total_messages,
                    messages_today: data.total_messages_today,
                    last_seen: data.uptime_stats.last_seen
                });
            }
        })
        .catch(error => console.error('Error fetching stats:', error));
}

// Add event listeners
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM content loaded, initializing...');
    
    // Store references to DOM elements
    consoleElement = document.getElementById('console');
    connectionStatus = document.getElementById('connection-status');
    
    document.getElementById('clear-console').addEventListener('click', () => {
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
    
    document.getElementById('refresh-stats').addEventListener('click', fetchStats);
    
    // Clean up logs button
    document.getElementById('cleanup-logs').addEventListener('click', () => {
        const button = document.getElementById('cleanup-logs');
        button.textContent = 'Cleaning...';
        button.disabled = true;
        
        // Use force=true parameter to force cleanup regardless of conditions
        fetch('/cleanup?force=true')
            .then(response => response.json())
            .then(data => {
                console.log('Cleanup result:', data);
                let message = '';
                if (data.error) {
                    message = `Error: ${data.error}`;
                } else {
                    message = `Cleaned up ${data.files_deleted} files, freed ${data.space_freed_mb.toFixed(2)} MB`;
                    if (data.forced) {
                        message += ' (forced cleanup)';
                        
                        // IMMEDIATELY update stats display without waiting for SSE
                        if (data.force_cleanup) {
                            document.getElementById('total-messages').textContent = "0";
                            document.getElementById('messages-today').textContent = "0";
                        }
                    }
                }
                
                const entry = document.createElement('div');
                entry.className = 'log-entry';
                entry.innerHTML = `<span class="timestamp">${new Date().toLocaleTimeString()}</span> <span class="status">SYSTEM</span> ${message}`;
                consoleElement.appendChild(entry);
                
                if (autoScroll) {
                    consoleElement.scrollTop = consoleElement.scrollHeight;
                }
                
                button.textContent = 'Clean Old Logs';
                button.disabled = false;
            })
            .catch(error => {
                console.error('Error during cleanup:', error);
                button.textContent = 'Clean Old Logs';
                button.disabled = false;
            });
    });
    
    // View storage info button
    document.getElementById('view-storage').addEventListener('click', () => {
        fetch('/storage')
            .then(response => response.json())
            .then(data => {
                console.log('Storage info:', data);
                
                const entry = document.createElement('div');
                entry.className = 'log-entry';
                entry.innerHTML = `
                    <span class="timestamp">${new Date().toLocaleTimeString()}</span> <span class="status">STORAGE</span>
                    <div style="margin-top:10px;">
                        <div>Data directory: ${(data.data_dir_size_mb).toFixed(2)} MB (${data.data_dir_file_count} files)</div>
                        <div>Disk usage: ${(data.disk_used_percent).toFixed(1)}% (${(data.disk_total_mb - data.disk_free_mb).toFixed(2)} MB used of ${(data.disk_total_mb).toFixed(2)} MB)</div>
                        <div>Free space: ${(data.disk_free_mb).toFixed(2)} MB</div>
                        <div>Cleanup settings: Max ${data.max_log_size_mb} MB or ${data.max_days_to_keep} days</div>
                        <div>Oldest file: ${data.oldest_file_date || 'none'}</div>
                    </div>
                `;
                consoleElement.appendChild(entry);
                
                if (autoScroll) {
                    consoleElement.scrollTop = consoleElement.scrollHeight;
                }
            })
            .catch(error => {
                console.error('Error getting storage info:', error);
            });
    });
    
    // Initialize
    console.log('Connecting to event source...');
    connectToEventSource();
    
    console.log('Fetching initial stats...');
    fetchStats();
    
    // Fetch new stats every minute
    setInterval(fetchStats, 60000);
    
    // Add any existing log messages
    fetch('/init-data')
        .then(response => response.json())
        .then(data => {
            console.log('Initial data:', data);
            if (data.messages) {
                data.messages.forEach(msg => addLogEntry(msg));
            }
        })
        .catch(error => console.error('Error fetching initial data:', error));
});