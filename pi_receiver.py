from flask import Flask, request, jsonify, render_template, Response
import datetime
import os
import json
import time
import threading
import queue

app = Flask(__name__)

# Configuration
LOG_FILENAME = "arduino_data.log"
DATA_DIRECTORY = "arduino_data"
MAX_MESSAGES = 100  # Maximum number of messages to keep in memory
MAX_LOG_SIZE_MB = 50  # Maximum size of log directory in MB
MAX_DAYS_TO_KEEP = 30  # Maximum number of days to keep logs

# Message queue for SSE (Server-Sent Events)
message_queue = queue.Queue(maxsize=MAX_MESSAGES)
latest_messages = []  # Store recent messages for new connections

# Ensure data directory exists
if not os.path.exists(DATA_DIRECTORY):
    os.makedirs(DATA_DIRECTORY)

# Ensure template and static directories exist
for dir_path in ['templates', 'static']:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

@app.route('/')
def dashboard():
    """Serve the dashboard page"""
    return render_template('dashboard.html')

@app.route('/data', methods=['POST'])
def receive_data():
    """Endpoint to receive forwarded data from relay server"""
    try:
        # Get the forwarded data
        data = request.get_json()
        
        # Generate timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Add Raspberry Pi receipt timestamp
        data['pi_timestamp'] = timestamp
        
        # Log to console
        print(f"\n{'='*50}")
        print(f"[{timestamp}] DATA RECEIVED FROM RELAY:")
        for key, value in data.items():
            print(f"  {key}: {value}")
        print('='*50)
        
        # Log to main log file
        with open(os.path.join(DATA_DIRECTORY, LOG_FILENAME), "a") as log_file:
            log_file.write(f"[{timestamp}] {json.dumps(data)}\n")
        
        # Save to daily JSON file
        save_to_daily_file(data)
        
        # Process the data
        process_data(data)
        
        # Add to message queue for live updates
        event_data = {
            'type': 'message', 
            'timestamp': timestamp, 
            'data': data
        }
        
        # Keep track of latest messages for new connections
        latest_messages.append(event_data)
        if len(latest_messages) > MAX_MESSAGES:
            latest_messages.pop(0)
        
        # Add to queue for SSE clients
        try:
            message_queue.put_nowait(json.dumps(event_data))
        except queue.Full:
            pass  # Queue is full, old clients will miss this message
        
        # Return success response
        return jsonify({
            "status": "success", 
            "message": "Data received by Raspberry Pi",
            "timestamp": timestamp
        }), 200
    
    except Exception as e:
        print(f"Error processing request: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

def save_to_daily_file(data):
    """Save data to a daily JSON file"""
    try:
        # Get today's date for filename
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        filename = f"arduino_data_{today}.json"
        filepath = os.path.join(DATA_DIRECTORY, filename)
        
        # Read existing data if file exists
        if os.path.exists(filepath):
            with open(filepath, 'r') as file:
                try:
                    daily_data = json.load(file)
                except json.JSONDecodeError:
                    # Handle case where file exists but isn't valid JSON
                    daily_data = {"data": []}
        else:
            daily_data = {"data": []}
        
        # Add new data
        daily_data["data"].append(data)
        
        # Write updated data back to file
        with open(filepath, 'w') as file:
            json.dump(daily_data, file, indent=2)
            
    except Exception as e:
        print(f"Error saving to daily file: {e}")

def clean_old_logs(force_cleanup=False):
    """Delete old log files and optionally reset statistics"""
    try:
        # Get current time for comparison
        now = datetime.datetime.now()
        today = now.strftime("%Y-%m-%d")
        
        # If force_cleanup is True, also reset the uptime stats
        if force_cleanup:
            try:
                # Reset uptime stats
                uptime_file = os.path.join(DATA_DIRECTORY, "uptime_stats.json")
                if os.path.exists(uptime_file):
                    # Reset statistics to zero but keep the file
                    stats = {
                        "last_seen": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "total_messages": 0,
                        "source_stats": {}
                    }
                    with open(uptime_file, 'w') as file:
                        json.dump(stats, file, indent=2)
                    print("Reset statistics to zero")
                
                # Also reset today's file
                today_file = os.path.join(DATA_DIRECTORY, f"arduino_data_{today}.json")
                if os.path.exists(today_file):
                    # Reset today's data to empty
                    with open(today_file, 'w') as file:
                        json.dump({"data": []}, file, indent=2)
                    print("Reset today's data file")
            except Exception as e:
                print(f"Error resetting stats: {str(e)}")
        
        # Check total size of data directory
        total_size = 0
        file_ages = {}
        
        for root, dirs, files in os.walk(DATA_DIRECTORY):
            for file in files:
                file_path = os.path.join(root, file)
                
                # Skip current day's data file and essential files
                if force_cleanup and (
                    file == "uptime_stats.json" or 
                    file == LOG_FILENAME
                ):
                    continue
                
                # Get file size in MB
                size_mb = os.path.getsize(file_path) / (1024 * 1024)
                total_size += size_mb
                
                # Get file modification time
                mtime = os.path.getmtime(file_path)
                file_datetime = datetime.datetime.fromtimestamp(mtime)
                days_old = (now - file_datetime).days
                
                file_ages[file_path] = {
                    'size_mb': size_mb,
                    'days_old': days_old
                }
        
        # If force_cleanup is True, mark all non-essential files for deletion
        files_to_delete = []
        
        if force_cleanup:
            # Add all files to deletion list except those we excluded above
            for file_path, info in file_ages.items():
                files_to_delete.append((file_path, info))
        else:
            # Standard cleanup logic based on age and size
            # First, add files older than MAX_DAYS_TO_KEEP
            for file_path, info in file_ages.items():
                if info['days_old'] > MAX_DAYS_TO_KEEP:
                    files_to_delete.append((file_path, info))
            
            # Sort remaining files by age (oldest first)
            if total_size > MAX_LOG_SIZE_MB:
                # Sort by age, oldest first
                sorted_files = sorted(file_ages.items(), key=lambda x: x[1]['days_old'], reverse=True)
                
                # Add files until we're under the limit
                size_to_remove = total_size - MAX_LOG_SIZE_MB
                size_removed = 0
                
                for file_path, info in sorted_files:
                    if file_path not in [f[0] for f in files_to_delete]:  # Skip if already marked for deletion
                        files_to_delete.append((file_path, info))
                        size_removed += info['size_mb']
                        if size_removed >= size_to_remove:
                            break
        
        # Now delete the files
        for file_path, info in files_to_delete:
            try:
                os.remove(file_path)
                print(f"Deleted old log file: {file_path} ({info['size_mb']:.2f} MB, {info['days_old']} days old)")
            except Exception as e:
                print(f"Error deleting file {file_path}: {str(e)}")
        
        return {
            'total_size_mb': total_size,
            'max_size_mb': MAX_LOG_SIZE_MB,
            'max_days': MAX_DAYS_TO_KEEP,
            'files_deleted': len(files_to_delete),
            'space_freed_mb': sum(info['size_mb'] for _, info in files_to_delete),
            'forced': force_cleanup
        }
        
    except Exception as e:
        print(f"Error cleaning old logs: {str(e)}")
        return {'error': str(e), 'forced': force_cleanup}

def process_data(data):
    """Process the received data"""
    # Record uptime statistics
    try:
        uptime_file = os.path.join(DATA_DIRECTORY, "uptime_stats.json")
        
        if os.path.exists(uptime_file):
            with open(uptime_file, 'r') as file:
                stats = json.load(file)
        else:
            stats = {
                "last_seen": None,
                "total_messages": 0,
                "source_stats": {}
            }
        
        # Update stats
        stats["last_seen"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stats["total_messages"] += 1
        
        # Track by source
        source = data.get("source", "unknown")
        if source not in stats["source_stats"]:
            stats["source_stats"][source] = 0
        stats["source_stats"][source] += 1
        
        # Save updated stats
        with open(uptime_file, 'w') as file:
            json.dump(stats, file, indent=2)
            
    except Exception as e:
        print(f"Error updating uptime stats: {e}")

@app.route('/stats', methods=['GET'])
def get_stats():
    """Return basic statistics about received data"""
    try:
        # Read uptime stats if available
        uptime_file = os.path.join(DATA_DIRECTORY, "uptime_stats.json")
        stats = {"error": "No statistics available yet"}
        
        if os.path.exists(uptime_file):
            with open(uptime_file, 'r') as file:
                stats = json.load(file)
        
        # Count total log entries
        log_file = os.path.join(DATA_DIRECTORY, LOG_FILENAME)
        if os.path.exists(log_file):
            with open(log_file, 'r') as file:
                line_count = sum(1 for _ in file)
        else:
            line_count = 0
            
        # Count messages today
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        today_file = os.path.join(DATA_DIRECTORY, f"arduino_data_{today}.json")
        today_count = 0
        
        if os.path.exists(today_file):
            with open(today_file, 'r') as file:
                try:
                    today_data = json.load(file)
                    today_count = len(today_data.get("data", []))
                except json.JSONDecodeError:
                    today_count = 0
            
        # Get list of daily files
        daily_files = [f for f in os.listdir(DATA_DIRECTORY) if f.startswith("arduino_data_") and f.endswith(".json")]
        
        response = {
            "uptime_stats": stats,
            "total_log_entries": line_count,
            "total_messages_today": today_count,
            "daily_files": daily_files
        }
        
        # Send stats update to SSE clients
        stats_event = {
            'type': 'stats',
            'stats': {
                'total_messages': stats.get('total_messages', 0),
                'messages_today': today_count,
                'last_seen': stats.get('last_seen', None)
            }
        }
        
        try:
            message_queue.put_nowait(json.dumps(stats_event))
        except queue.Full:
            pass
            
        return jsonify(response)
    
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/events')
def events():
    """SSE endpoint for live updates"""
    def generate():
        # Send headers for SSE
        yield "retry: 10000\n\n"
        
        # Send any existing messages to new clients
        for msg in latest_messages:
            yield f"data: {json.dumps(msg)}\n\n"
        
        while True:
            try:
                # Get message from queue, timeout after 30 seconds for keepalive
                message = message_queue.get(timeout=30)
                yield f"data: {message}\n\n"
            except queue.Empty:
                # Send keepalive comment
                yield ": keepalive\n\n"
                
    return Response(generate(), mimetype="text/event-stream")

@app.route('/init-data')
def init_data():
    """Return initial data for new dashboard connections"""
    return jsonify({
        "messages": latest_messages
    })

@app.route('/cleanup', methods=['GET', 'POST'])
def cleanup_logs():
    """Manually trigger log cleanup"""
    # When accessed through POST or with force=true parameter, force cleanup
    force_cleanup = request.method == 'POST' or request.args.get('force') == 'true'
    result = clean_old_logs(force_cleanup=force_cleanup)
    
    # If it was a forced cleanup, send updated stats to all clients IMMEDIATELY
    if force_cleanup:
        try:
            # Send stats update to SSE clients with priority
            stats_event = {
                'type': 'stats',
                'stats': {
                    'total_messages': 0,  # Reset to zero
                    'messages_today': 0,  # Also reset today's count for immediate feedback
                    'last_seen': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }
            
            # Clear the queue to make room for our urgent message
            while not message_queue.empty():
                try:
                    message_queue.get_nowait()
                except:
                    pass
                    
            # Put our stats update at the front
            try:
                message_queue.put_nowait(json.dumps(stats_event))
            except queue.Full:
                pass
                
        except Exception as e:
            print(f"Error sending stats update: {e}")
    
    # Add force status to the result for the client
    result['force_cleanup'] = force_cleanup
    return jsonify(result)

@app.route('/storage', methods=['GET'])
def storage_info():
    """Get storage information"""
    try:
        # Calculate total size of data directory
        total_size = 0
        file_count = 0
        oldest_file = None
        oldest_timestamp = None
        
        for root, dirs, files in os.walk(DATA_DIRECTORY):
            for file in files:
                file_path = os.path.join(root, file)
                size = os.path.getsize(file_path)
                total_size += size
                file_count += 1
                
                # Check if it's the oldest file
                mtime = os.path.getmtime(file_path)
                if oldest_timestamp is None or mtime < oldest_timestamp:
                    oldest_timestamp = mtime
                    oldest_file = file_path
        
        # Get disk space information
        disk = os.statvfs(DATA_DIRECTORY)
        free_bytes = disk.f_frsize * disk.f_bavail
        total_bytes = disk.f_frsize * disk.f_blocks
        
        return jsonify({
            "data_dir_size_mb": total_size / (1024 * 1024),
            "data_dir_file_count": file_count,
            "oldest_file": oldest_file,
            "oldest_file_date": datetime.datetime.fromtimestamp(oldest_timestamp).strftime("%Y-%m-%d %H:%M:%S") if oldest_timestamp else None,
            "disk_free_mb": free_bytes / (1024 * 1024),
            "disk_total_mb": total_bytes / (1024 * 1024),
            "disk_used_percent": 100 - (free_bytes / total_bytes * 100),
            "max_log_size_mb": MAX_LOG_SIZE_MB,
            "max_days_to_keep": MAX_DAYS_TO_KEEP
        })
    
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    # Create log file if it doesn't exist
    log_path = os.path.join(DATA_DIRECTORY, LOG_FILENAME)
    if not os.path.exists(log_path):
        with open(log_path, "w") as f:
            f.write("=== Arduino Data Log ===\n")
    
    # Run initial cleanup
    cleanup_result = clean_old_logs()
    
    print("\n" + "*"*60)
    print("*  RASPBERRY PI ARDUINO DATA DASHBOARD")
    print("*  " + "-"*45)
    print(f"*  Web Dashboard:     http://0.0.0.0:8000/")
    print(f"*  Data Endpoint:     http://0.0.0.0:8000/data")
    print(f"*  Stats Endpoint:    http://0.0.0.0:8000/stats")
    print(f"*  Storage Endpoint:  http://0.0.0.0:8000/storage")
    print(f"*  Cleanup Endpoint:  http://0.0.0.0:8000/cleanup")
    print(f"*  Data directory:    {os.path.abspath(DATA_DIRECTORY)}")
    print(f"*  Log file:          {os.path.abspath(log_path)}")
    print(f"*  Max log size:      {MAX_LOG_SIZE_MB} MB")
    print(f"*  Max days to keep:  {MAX_DAYS_TO_KEEP} days")
    print("*"*60 + "\n")
    
    if 'error' not in cleanup_result:
        print(f"Initial cleanup: {cleanup_result['files_deleted']} files deleted, {cleanup_result['space_freed_mb']:.2f} MB freed")
    
    print("Server is running. Press Ctrl+C to stop.")
    
    # Set up a background thread to periodically clean logs
    def cleanup_thread():
        while True:
            # Sleep for 1 hour
            time.sleep(3600)
            # Run cleanup
            clean_old_logs()
    
    cleanup_bg = threading.Thread(target=cleanup_thread, daemon=True)
    cleanup_bg.start()
    
    # Run the server
    app.run(host='0.0.0.0', port=8000, debug=True)