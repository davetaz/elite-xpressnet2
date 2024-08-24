import asyncio
import websockets
import json
import threading
import time
from dotenv import load_dotenv
import os
import requests
import netifaces as ni
import xpressNet
from mockController import MockHornbyController  # Import the MockHornbyController

# Load environment variables from .env file
load_dotenv()

CONTROL_KEY = os.getenv('CONTROL_KEY')
NODE_SERVER_URL = os.getenv('NODE_SERVER_URL')

connected_clients = set()

class RealHornbyController:
    def __init__(self, device_path, baud_rate, message_delay, response_handler):
        try:
            xpressNet.connection_open(device_path, baud_rate, message_delay, response_handler)
            self.trains = {}
            self.accessories = {}
        except ImportError:
            raise ImportError("xpressNet library not installed. Please install it to use the real controller.")

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

    def accessory(self, accessory_number, direction):
        try:
            accessory = self.get_accessory(accessory_number)
            if direction == "FORWARD":
                accessory.activateOutput2()
            elif direction == "REVERSE":
                accessory.activateOutput1()
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

# Check if the real controller is available
def is_real_controller_available():
    try:
        xpressNet.connection_open('/dev/ttyACM0', 19200, 0.25, response_handler)
        return True
    except ImportError:
        return False
    except Exception as e:
        return False

# Create the appropriate controller based on availability
if is_real_controller_available():
    print(" * Connected to xPressNet controller")
    controller = RealHornbyController('/dev/ttyACM0', 19200, 0.25, response_handler)
else:
    print(" * Using mock controller")
    controller = MockHornbyController()

def get_local_ip():
    gateways = ni.gateways()
    default_gateway = gateways['default'][ni.AF_INET][1]
    return ni.ifaddresses(default_gateway)[ni.AF_INET][0]['addr']

def get_global_ips():
    try:
        global_ipv4 = requests.get('https://api.ipify.org').text
        global_ipv6 = requests.get('https://api64.ipify.org').text
        return global_ipv4, global_ipv6
    except Exception as e:
        print(f'Error getting global IPs: {e}')
        return None, None

def send_server_status():
    local_ip = get_local_ip()
    global_ipv4, global_ipv6 = get_global_ips()
    last_reported = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())

    headers = {'Authorization': f'Bearer {CONTROL_KEY}'}
    data = {
        'localIP': local_ip,
        'globalIPv4': global_ipv4,
        'globalIPv6': global_ipv6,
        'lastReported': last_reported
    }
    try:
        response = requests.post(NODE_SERVER_URL, json=data, headers=headers)
        if response.status_code == 200:
            print('Server status updated successfully.')
        else:
            print(f'Failed to update server status: {response.status_code}')
    except requests.exceptions.RequestException as e:
        print(f'Error updating server status: {e}')

async def websocket_handler(websocket, path):
    print("Client connected")
    # Add the new connection to the set of connected clients
    connected_clients.add(websocket)

    try:
        async for message in websocket:
            data = json.loads(message)
            action = data.get('action')

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

                # Send throttle command to the controller and get the response
                controller.throttle(train_number, speed, direction)

            elif action == 'stop':
                train_number = data['train_number']
                print(f'Stop: Train: {train_number}')

                # Send stop command to the controller and get the response
                controller.stop(train_number)

            elif action == 'getState':
                train_number = data['train_number']
                print(f'getState: Train: {train_number}')

                # Send stop command to the controller and get the response
                controller.getState(train_number)

            elif action == 'function':
                train_number = data['train_number']
                function_id = data['function_id']
                switch = data['switch']
                print(f'Function: Train: {train_number} | Function ID: {function_id} | Switch: {switch}')

                # Send function command to the controller and get the response
                controller.function(train_number, function_id, switch)

            elif action == 'accessory':
                accessory_number = data['accessory_number']
                direction = data['direction']
                print(f'Accessory: Accessory: {accessory_number} | Direction: {direction}')

                # Send accessory command to the controller and get the response
                controller.accessory(accessory_number, direction)

            elif action == 'controller_status':
                status = 'online' if is_real_controller_available() else 'offline'
                await websocket.send(json.dumps({
                    'type': 'controller_status',
                    'status': status
                }))

    except websockets.ConnectionClosed:
        print("Client disconnected")
    finally:
        # Remove the client from the connected clients set when they disconnect
        connected_clients.remove(websocket)

# Utility function to broadcast messages to all connected clients
async def broadcast_message(message):
    if connected_clients:  # Only try to broadcast if there are connected clients
        message_json = json.dumps(message)
        # Create a list of tasks, ensuring each send call is turned into a Task
        tasks = [asyncio.create_task(client.send(message_json)) for client in connected_clients]
        await asyncio.gather(*tasks)  # Wait for all tasks to complete

async def main():
    async with websockets.serve(websocket_handler, "0.0.0.0", 8080):
        print("WebSocket server started")
        await asyncio.Future()  # run forever

# Periodically check if the real controller becomes available or unavailable
def controller_availability_check():
    global controller
    while True:
        if is_real_controller_available():
            if not isinstance(controller, RealHornbyController):
                print("Real controller detected. Switching to real controller.")
                controller = RealHornbyController('/dev/ttyACM0', 19200, 0.25, response_handler)
            status = 'online'
        else:
            if not isinstance(controller, MockHornbyController):
                print("Real controller not available. Switching to mock controller.")
                controller = MockHornbyController()
            status = 'offline'
        #send_server_status()
        time.sleep(60)  # Check every 60 seconds

if __name__ == '__main__':
    availability_check_thread = threading.Thread(target=controller_availability_check)
    availability_check_thread.daemon = True
    availability_check_thread.start()

    asyncio.run(main())