from flask import Flask, request, jsonify, render_template, Response
import datetime
import os
import json
import time
import threading
import queue
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("smart_room.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SmartRoomServer")

app = Flask(__name__)

# Configuration
DATA_DIRECTORY = "smart_room_data"
MAX_MESSAGES = 100  # Maximum number of messages to keep in memory

# System state
system_state = {
    "door_state": False,  # False = closed, True = open
    "light_state": False,  # False = off, True = on
    "user_present": False,  # Is a registered user in the room?
    "luminosity": 0,  # Current light level
    "last_update": None,  # Timestamp of last update
    "detected_user": None,  # ID of detected user (if any)
    "users_in_room": [],  # List of users currently in room
}

# User database (in real implementation, this would be in a proper database)
users = {
    "user001": {"name": "Alice", "authorized": True},
    "user002": {"name": "Bob", "authorized": True},
    "user003": {"name": "Charlie", "authorized": True}
}

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

def process_arduino_data(data_str):
    """Process data received from Arduino"""
    global system_state
    
    try:
        data = json.loads(data_str) if isinstance(data_str, str) else data_str
        
        # Generate timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Add receipt timestamp
        data['pi_timestamp'] = timestamp
        
        # Log to console
        logger.info(f"Data received from relay server: {data}")
        
        # Update system state
        if "door" in data:
            door_value = data["door"]
            # Handle different formats of door state
            if isinstance(door_value, bool):
                system_state["door_state"] = door_value
            elif isinstance(door_value, str):
                system_state["door_state"] = (door_value.lower() == "open")
        
        if "light" in data:
            light_value = data["light"]
            # Handle different formats of light state
            if isinstance(light_value, bool):
                system_state["light_state"] = light_value
            elif isinstance(light_value, str):
                system_state["light_state"] = (light_value.lower() == "on")
        
        if "user_present" in data:
            old_user_present = system_state["user_present"]
            system_state["user_present"] = data["user_present"]
            
            # User entry/exit logic
            if not old_user_present and system_state["user_present"]:
                # User entered room
                handle_user_entry()
            elif old_user_present and not system_state["user_present"]:
                # User left room
                handle_user_exit()
        
        if "luminosity" in data:
            system_state["luminosity"] = data["luminosity"]
        
        system_state["last_update"] = timestamp
        
        # Save to daily log
        save_to_daily_file(data)
        
        # Add to message queue for live updates
        event_data = {
            'type': 'update', 
            'timestamp': timestamp, 
            'data': data,
            'system_state': system_state
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
        
        return data
        
    except json.JSONDecodeError:
        logger.warning(f"Received non-JSON data: {data_str}")
    except Exception as e:
        logger.error(f"Error processing data: {e}")
    
    return None

def handle_user_entry():
    """Handle logic when a user enters the room"""
    # In a real implementation, this would identify the specific user
    # For now, we'll simulate detecting the first user in our database
    if len(system_state["users_in_room"]) == 0:
        user_id = list(users.keys())[0]
        system_state["detected_user"] = user_id
        system_state["users_in_room"].append(user_id)
        
        # Log the event
        logger.info(f"User {users[user_id]['name']} entered the room")
        
        # Send welcome event for display
        welcome_event = {
            'type': 'welcome',
            'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'user_id': user_id,
            'user_name': users[user_id]['name']
        }
        
        try:
            message_queue.put_nowait(json.dumps(welcome_event))
        except queue.Full:
            pass

def handle_user_exit():
    """Handle logic when a user exits the room"""
    # In a real implementation, this would identify which specific user left
    # For now, we'll simulate the last user leaving
    if len(system_state["users_in_room"]) > 0:
        user_id = system_state["users_in_room"].pop()
        
        # If this was the last user, clear detected_user
        if len(system_state["users_in_room"]) == 0:
            system_state["detected_user"] = None
        
        # Log the event
        logger.info(f"User {users[user_id]['name']} left the room")

def save_to_daily_file(data):
    """Save data to a daily JSON file"""
    try:
        # Get today's date for filename
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        filename = f"smart_room_{today}.json"
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
        logger.error(f"Error saving to daily file: {e}")

@app.route('/')
def dashboard():
    """Serve the dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/state', methods=['GET', 'POST'])
def api_state():
    """Handle system state - both retrieval and updates"""
    # For GET requests, return current system state
    if request.method == 'GET':
        return jsonify(system_state)
    
    # For POST requests, process incoming data
    elif request.method == 'POST':
        try:
            # Get data from request
            data = request.get_json()
            if data:
                # Process the data
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"Data received via API: {data}")
                
                # Process the data
                process_arduino_data(data)
                
                # Return success response
                return jsonify({
                    "status": "success",
                    "message": "Data received and processed",
                    "timestamp": timestamp,
                    "updated_state": system_state
                })
            else:
                return jsonify({"status": "error", "message": "No data provided"}), 400
        except Exception as e:
            logger.error(f"Error processing API data: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/users', methods=['GET'])
def get_users():
    """Return list of users"""
    return jsonify(users)

@app.route('/api/light/control', methods=['POST'])
def control_light():
    """Control light remotely"""
    try:
        data = request.get_json()
        command = data.get('command')
        
        if command not in ['on', 'off']:
            return jsonify({"status": "error", "message": "Invalid command"}), 400
        
        # Check if we can turn off the light
        if command == 'off' and system_state["user_present"]:
            return jsonify({
                "status": "error", 
                "message": "Cannot turn off light while users are in the room"
            }), 403
        
        # Update light state directly
        system_state["light_state"] = (command == 'on')
        
        # Send light state update
        light_event = {
            'type': 'light_control',
            'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'command': command,
            'success': True
        }
        
        try:
            message_queue.put_nowait(json.dumps(light_event))
        except queue.Full:
            pass
        
        return jsonify({
            "status": "success", 
            "message": f"Light turned {command}",
            "state": system_state
        })
            
    except Exception as e:
        logger.error(f"Error in light control: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/mobile/register', methods=['POST'])
def register_mobile():
    """Register a mobile device for a user"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        device_token = data.get('device_token')
        user_name = data.get('user_name')
        
        # Validate input
        if not user_id or not device_token:
            return jsonify({"status": "error", "message": "Missing required fields"}), 400
        
        # Check if user exists, if not create them
        if user_id not in users:
            users[user_id] = {
                "name": user_name or f"User {user_id}",
                "authorized": True,
                "device_token": device_token
            }
            logger.info(f"New user registered: {user_id}")
        else:
            # Update existing user
            users[user_id]["device_token"] = device_token
            if user_name:
                users[user_id]["name"] = user_name
            logger.info(f"Updated user registration: {user_id}")
        
        return jsonify({
            "status": "success", 
            "message": "Device registered successfully",
            "user": users[user_id]
        })
        
    except Exception as e:
        logger.error(f"Error in mobile registration: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/events')
def events():
    """SSE endpoint for live updates"""
    def generate():
        # Send headers for SSE
        yield "retry: 10000\n\n"
        
        # Send initial system state
        initial_state = {
            'type': 'initial_state',
            'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'system_state': system_state
        }
        yield f"data: {json.dumps(initial_state)}\n\n"
        
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

if __name__ == '__main__':
    # Run the server
    logger.info("Starting Smart Room Server")
    print("\n" + "*"*60)
    print("*  SMART ROOM CONTROL SYSTEM")
    print("*  " + "-"*45)
    print(f"*  Web Dashboard:     http://0.0.0.0:8000/")
    print(f"*  API Endpoint:      http://0.0.0.0:8000/api/state")
    print(f"*  Mobile API:        http://0.0.0.0:8000/api/mobile")
    print(f"*  Data directory:    {os.path.abspath(DATA_DIRECTORY)}")
    print("*"*60 + "\n")
    
    app.run(host='0.0.0.0', port=8000, debug=True, use_reloader=False)
