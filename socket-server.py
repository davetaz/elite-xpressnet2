import asyncio
import websockets
import json
import threading
import time
import socket
import os
import serial  # Ensure the import is correct for serial communication
from zeroconf import ServiceInfo, Zeroconf
from dotenv import load_dotenv
import xpressNet
from http_server import start_http_server  # Import the HTTP server module

# Load environment variables from config.env
load_dotenv("config.env")

controller_lock = threading.Lock()
controller = None
connected_clients = set()
accessory_states = {}  # Dictionary to store accessory states by accessoryID

class XpressNetController:
    def __init__(self, device_path, baud_rate, message_delay, response_handler):
        try:
            xpressNet.connection_open(device_path, baud_rate, message_delay, response_handler)
            self.trains = {}
            self.accessories = {}
        except ImportError:
            raise ImportError("xpressNet library not installed. Please install it to use the real controller.")

    def is_controller_connected(self):
        """Check if the controller is connected."""
        return xpressNet.is_controller_connected()

    def getStatus(self):
        xpressNet.getStatus()

    def getVersion(self):
        xpressNet.getVersion()

    def emergencyOff(self):
        xpressNet.emergencyOff()

    def resumeNormalOperations(self):
        xpressNet.resumeNormalOperations()

    def get_train(self, train_number):
        if train_number not in self.trains:
            self.trains[train_number] = xpressNet.Train(train_number)
        return self.trains[train_number]

    def throttle(self, train_number, speed, direction):
        train = self.get_train(train_number)
        train.throttle(speed, direction)
        return train.getState()

    def stop(self, train_number):
        train = self.get_train(train_number)
        train.stop()
        return train.getState()

    def function(self, train_number, function_id, switch):
        train = self.get_train(train_number)
        train.function(function_id, switch)
        return train.getState()

    def getState(self, train_number):
        train = self.get_train(train_number)
        return train.getState()

    def setAccessoryDirection(self, accessory_number, direction):
        try:
            accessory = self.get_accessory(accessory_number)
            if direction == "FORWARD":
                accessory.activateOutput1()
            elif direction == "REVERSE":
                accessory.activateOutput2()
            else:
                return {"status_code": 400, "message": "Invalid accessory direction"}
            return {"status_code": 200, "message": "Accessory command sent successfully"}
        except Exception as e:
            return {"status_code": 500, "message": f"Error sending accessory command: {str(e)}"}

    def get_accessory(self, accessory_number):
        if accessory_number not in self.accessories:
            self.accessories[accessory_number] = xpressNet.Accessory(accessory_number)
        return self.accessories[accessory_number]

# Define a callback function to handle messages and forward them to all clients
def response_handler(message):
    asyncio.run(broadcast_message(json.loads(message)))

def is_controller_available():
    try:
        xpressNet.connection_open('/dev/ttyACM0', 19200, 0.25, response_handler)
        return True
    except ImportError:
        return False
    except Exception as e:
        return False

# Function to get local IP address
def get_local_ip():
    """Get the local IP address of the machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connect to an external server, does not need to be reachable
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

# Function to send status updates to all connected clients
async def send_status_update():
    response = {
        "status_code": 200,
        "message": "SocketStatus",
        "data": {
            "Ready": True,
            "Clients": len(connected_clients),
            "Controller_Connected": controller is not None
        }
    }
    await broadcast_message(response)

async def websocket_handler(websocket, path):
    connected_clients.add(websocket)

    # Send status update when a new client connects
    await send_status_update()

    try:
        async for message in websocket:
            data = json.loads(message)
            action = data.get('action')

            if controller is None:
                await websocket.send(json.dumps({
                    'type': 'controller_status',
                    'status': "offline"
                }))
                continue

            # Check if the controller is connected
            if not controller.is_controller_connected():
                await websocket.send(json.dumps({
                    'type': 'controller_status',
                    'status': "offline"
                }))
                continue

            if action == 'getControllerStatus':
                controller.getStatus()

            if action == 'getControllerVersion':
                controller.getVersion()

            if action == 'emergencyOff':
                controller.emergencyOff()

            if action == 'resumeNormalOperations':
                controller.resumeNormalOperations()

            if action == 'throttle':
                train_number = data['train_number']
                speed = data['speed']
                direction = data['direction']
                print(f'Throttle: Train: {train_number} | Speed: {speed} | Direction: {direction}')

                controller.throttle(train_number, speed, direction)

            elif action == 'stop':
                train_number = data['train_number']
                print(f'Stop: Train: {train_number}')

                controller.stop(train_number)

            elif action == 'getState':
                train_number = data['train_number']
                print(f'getState: Train: {train_number}')

                controller.getState(train_number)

            elif action == 'function':
                train_number = data['train_number']
                function_id = data['function_id']
                switch = data['switch']
                print(f'Function: Train: {train_number} | Function ID: {function_id} | Switch: {switch}')

                controller.function(train_number, function_id, switch)

            elif action == 'setAccessoryDirection':
                accessory_number = data['accessory_number']
                direction = data['direction']
                print(f'Accessory: Accessory: {accessory_number} | Direction: {direction}')

                controller.setAccessoryDirection(accessory_number, direction)

            elif action == 'setAccessoryState':
                accessory_id = data['accessory_id']
                state = data['state']
                print(f'Set Accessory State: Accessory ID: {accessory_id} | State: {state}')

                # Store the state and broadcast to all clients
                accessory_states[accessory_id] = state
                await broadcast_message({
                    "message": "accessoryState",
                    "status_code": 200,
                    "accessory_id": accessory_id,
                    "state": state
                })

            elif action == 'getAccessoryState':
                accessory_id = data['accessory_id']
                print(f'Get Accessory State: Accessory ID: {accessory_id}')

                state = accessory_states.get(accessory_id, {})
                await broadcast_message({
                    "message": "accessoryState",
                    "status_code": 200,
                    "accessory_id": accessory_id,
                    "state": state
                })

            elif action == 'getAccessoryStates':
                print('Get Accessory States')
                print(accessory_states)
                await broadcast_message({
                    "message": "accessoryStates",
                    "status_code": 200,
                    "accessories": accessory_states
                })

            elif action == 'controller_status':
                status = 'online' if is_controller_available() else 'offline'
                await websocket.send(json.dumps({
                    'type': 'controller_status',
                    'status': status
                }))

    except websockets.ConnectionClosed:
        print("Client disconnected")
    finally:
        connected_clients.remove(websocket)
        # Send status update when a client disconnects
        await send_status_update()

# Utility function to broadcast messages to all connected clients
async def broadcast_message(message):
    if connected_clients:
        message_json = json.dumps(message)
        tasks = [asyncio.create_task(client.send(message_json)) for client in connected_clients]
        await asyncio.gather(*tasks)

async def main():
    async with websockets.serve(websocket_handler, "0.0.0.0", 8080):
        print("WebSocket server started")
        await asyncio.Future()  # run forever

# (Your XpressNetController class and other functions remain the same...)

def set_controller(new_controller):
    global controller
    with controller_lock:
        controller = new_controller

def get_controller():
    global controller
    with controller_lock:
        return controller

def start_mdns_advertising():
    local_ip = get_local_ip()
    hostname = socket.gethostname()

    # Define the service information
    desc = {'path': '/'}
    info = ServiceInfo(
        "_http._tcp.local.",
        "xpressNetControl._http._tcp.local.",
        addresses=[socket.inet_aton(local_ip)],
        port=8080,
        properties=desc,
        server=f"{hostname}.local.",
    )

    # Start the zeroconf service
    zeroconf = Zeroconf()
    zeroconf.register_service(info)
    print(f"mDNS service registered: xpressNetControl on {local_ip} ({hostname}.local)")

def controller_availability_check():
    # Call set_controller once at the start
    if get_controller() is None:
        print("Setting up controller...")
        set_controller(XpressNetController('/dev/ttyACM0', 19200, 0.25, response_handler))

    was_connected = False  # Tracks the previous connection state

    while True:
        # Periodically check if the controller is connected
        if get_controller().is_controller_connected():
            if not was_connected:  # Only print when recovering from a disconnect
                print("Controller is connected.")
            was_connected = True  # Update the state
        else:
            if was_connected:  # Only print when transitioning to a disconnected state
                print("Controller is disconnected!")
            was_connected = False  # Update the state
            # Handle disconnection logic if needed, e.g., send a status update
            asyncio.run(send_status_update())

        time.sleep(10)  # Check every 10 seconds

if __name__ == '__main__':
    # Start mDNS/Bonjour advertising
    start_mdns_advertising()

        # Check if HTTP server is enabled in the config
    if os.getenv("HTTP_SERVER_ENABLE", "FALSE").upper() == "TRUE":
        # Start HTTP server in a separate thread
        http_server_thread = threading.Thread(target=start_http_server, args=(get_controller, get_local_ip()))
        http_server_thread.daemon = True
        http_server_thread.start()

    availability_check_thread = threading.Thread(target=controller_availability_check)
    availability_check_thread.daemon = True
    availability_check_thread.start()

    asyncio.run(main())