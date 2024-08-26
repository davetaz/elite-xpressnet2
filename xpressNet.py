import logging
import serial
import threading
import struct
from functools import reduce
import json
import time

# Constants for direction
REVERSE = 0
FORWARD = 1
OFF = 0
ON = 1

# Global variables for serial communication
ser = None
lock = threading.Lock()
buffer = bytearray()
delay_between_commands = 0.25  # Default delay in seconds between commands
listening = True  # Flag to control the listening thread

# Callback for processed messages
callback = None

function_table = []

# Global dictionary to store active Train instances
train_instances = {}

# Global variable to store the last requested train state address
last_requested_train_address = None

# Global variable to track if the first response has been processed
first_response_processed = False

# Calculate checksum
def calculate_checksum(data):
    return reduce(lambda r, v: r ^ v, data)

# Convert data to hex string for logging
def to_hex(data):
    return ''.join(f'{c:02X}' for c in data)

# Send data over serial
def send(data):
    global ser
    if ser is None:
        raise XpressNetException("Connection not open")
    buffer = bytearray(data)
    checksum = calculate_checksum(buffer)
    buffer.append(checksum)
    with lock:
        logging.debug(f"Sending: {to_hex(buffer)}")
        ser.write(buffer)

# Receive data and process buffer
def receive():
    global ser, listening
    while listening:
        with lock:
            if ser.in_waiting > 0:
                try:
                    data = ser.read(ser.in_waiting)  # Read all available bytes
                    logging.debug(f"Received: {to_hex(data)}")
                    buffer.extend(data)  # Add to the buffer
                    process_data()  # Process the buffer
                except serial.SerialException as e:
                    logging.error(f"Serial exception during reception: {e}")
                    listening = False
                except OSError as e:
                    logging.error(f"OSError during reception: {e}")
                    listening = False

def decode_train_number(high_byte, low_byte):
    if high_byte < 0xC0:  # Addresses less than 100
        return low_byte
    else:  # Addresses from 100 to 9999
        return ((high_byte & 0x3F) << 8) | low_byte

# Process received data
def process_data():
    global buffer, train_instances, first_response_processed
    while len(buffer) > 0:
        header_byte = buffer[0]
        chunk_size = (header_byte & 0x0F) + 2  # Calculate chunk size from the last nibble + 2 (header + data bytes)

        if len(buffer) >= chunk_size:  # Check if we have enough bytes in the buffer to process this chunk
            chunk = buffer[:chunk_size]
            response = {
                "status_code": 200,
                "message": None,
                "data": {},
                "debug": f"{to_hex(chunk)}"
            }

            # Handle Loco Status Message (Function and Speed/Direction) returned from Elite after request
            if chunk[0] == 0xE5 and len(chunk) >= 7:
                identification_byte = chunk[1]

                # Extract Train Number
                train_number = decode_train_number(chunk[2], chunk[3])

                # Ensure the train instance exists
                if train_number not in train_instances:
                    train_instances[train_number] = Train(train_number)

                train = train_instances[train_number]

                if identification_byte == 0xF9:
                    # Function message
                    response["message"] = "Loco Function Status"
                    response["action"] = "function"
                    response["data"]["train_number"] = train_number

                    # Decode Function Group 1 (F0-F4) and Function Group 2 (F5-F12)
                    function_group_0 = chunk[4]
                    function_group_1 = chunk[5]

                    functions = {
                        "0": bool(function_group_0 & 0x10),
                        "1": bool(function_group_0 & 0x01),
                        "2": bool(function_group_0 & 0x02),
                        "3": bool(function_group_0 & 0x04),
                        "4": bool(function_group_0 & 0x08),
                        "5": bool(function_group_1 & 0x01),
                        "6": bool(function_group_1 & 0x02),
                        "7": bool(function_group_1 & 0x04),
                        "8": bool(function_group_1 & 0x08),
                        "9": bool(function_group_1 & 0x10),
                        "10": bool(function_group_1 & 0x20),
                        "11": bool(function_group_1 & 0x40),
                        "12": bool(function_group_1 & 0x80),
                    }

                    response["data"]["functions"] = functions

                    # Update train state
                    train.update_functions(functions)

                elif identification_byte == 0xF8:
                    # Speed and direction message
                    response["message"] = "Loco Speed/Direction Status"
                    response["action"] = "throttle"
                    response["data"]["train_number"] = train_number
                    speed_direction_byte = chunk[5]
                    direction = REVERSE if speed_direction_byte < 0x80 else FORWARD
                    speed = speed_direction_byte & 0x7F  # Extract the lower 7 bits for speed (0-127)

                    response["data"]["direction"] = "Forward" if direction == FORWARD else "Reverse"
                    response["data"]["speed"] = speed

                    # Update train state
                    train.update_throttle(speed, direction)

            # Handle loco state message (returned from Elite after getState request, e.g. E40095000071 - No address!)
            elif chunk[0] == 0xE4 and len(chunk) >= 6:
                identification_byte = chunk[1]
                if last_requested_train_address is not None:
                    response["message"] = "Loco State"
                    response["action"] = "getState"
                    # Handle the response using the last requested address
                    train_number = last_requested_train_address
                    response["data"]["train_number"] = train_number

                    # Ensure the train instance exists
                    if train_number not in train_instances:
                        train_instances[train_number] = Train(train_number)

                    train = train_instances[train_number]

                    speed_direction_byte = chunk[2]
                    direction = REVERSE if speed_direction_byte < 0x80 else FORWARD
                    speed = speed_direction_byte & 0x7F  # Extract the lower 7 bits for speed (0-127)

                    response["data"]["direction"] = "Forward" if direction == FORWARD else "Reverse"
                    response["data"]["speed"] = speed

                    # Decode Function Group 1 (F0-F4) and Function Group 2 (F5-F12)
                    function_group_0 = chunk[3]
                    function_group_1 = chunk[4]

                    functions = {
                        "0": bool(function_group_0 & 0x10),
                        "1": bool(function_group_0 & 0x01),
                        "2": bool(function_group_0 & 0x02),
                        "3": bool(function_group_0 & 0x04),
                        "4": bool(function_group_0 & 0x08),
                        "5": bool(function_group_1 & 0x01),
                        "6": bool(function_group_1 & 0x02),
                        "7": bool(function_group_1 & 0x04),
                        "8": bool(function_group_1 & 0x08),
                        "9": bool(function_group_1 & 0x10),
                        "10": bool(function_group_1 & 0x20),
                        "11": bool(function_group_1 & 0x40),
                        "12": bool(function_group_1 & 0x80),
                    }

                    # Update train state
                    train.update_throttle(speed, direction)
                    train.update_functions(functions)

                    # Add functions 13-28 from the train's cached state
                    for i in range(13, 29):
                        group_index, _, bitmask = function_table[i]
                        functions[str(i)] = bool(train.group[group_index] & bitmask)

                    response["data"]["functions"] = functions

                    # Mark the first response as processed
                    first_response_processed = True

            # Handle loco state message for functions F13-F28
            elif chunk[0] == 0xE3 and len(chunk) >= 5:
                identification_byte = chunk[1]
                if last_requested_train_address is not None:
                    response["message"] = "Loco State"
                    response["action"] = "getState"
                    # Handle the response using the last requested address
                    train_number = last_requested_train_address
                    response["data"]["train_number"] = train_number

                    # Ensure the train instance exists
                    if train_number not in train_instances:
                        train_instances[train_number] = Train(train_number)

                    train = train_instances[train_number]

                    # Decode Function Group 3 (F13-F20) and Function Group 4 (F21-F28)
                    function_group_2 = chunk[2]
                    function_group_3 = chunk[3]

                    functions = {
                        "13": bool(function_group_2 & 0x01),
                        "14": bool(function_group_2 & 0x02),
                        "15": bool(function_group_2 & 0x04),
                        "16": bool(function_group_2 & 0x08),
                        "17": bool(function_group_2 & 0x10),
                        "18": bool(function_group_2 & 0x20),
                        "19": bool(function_group_2 & 0x40),
                        "20": bool(function_group_2 & 0x80),
                        "21": bool(function_group_3 & 0x01),
                        "22": bool(function_group_3 & 0x02),
                        "23": bool(function_group_3 & 0x04),
                        "24": bool(function_group_3 & 0x08),
                        "25": bool(function_group_3 & 0x10),
                        "26": bool(function_group_3 & 0x20),
                        "27": bool(function_group_3 & 0x40),
                        "28": bool(function_group_3 & 0x80),
                    }

                    # Update train state
                    train.update_functions(functions)

                    for i in range(0, 13):
                        group_index, _, bitmask = function_table[i]
                        functions[str(i)] = bool(train.group[group_index] & bitmask)

                    response["data"]["functions"] = functions

            # Handle Command Station Status Response (200 OK)
            elif chunk[0] == 0x62 and chunk[1] == 0x22 and len(chunk) >= 3:
                status_byte = chunk[2]
                response["message"] = "Status"
                response["data"] = {
                    "Ready": status_byte == 0x00,
                    "Emergency_Off": bool(status_byte & 0x01),
                    "Emergency_Stop": bool(status_byte & 0x02),
                    "Auto_Start": bool(status_byte & 0x04),
                    "Service_Mode": bool(status_byte & 0x08),
                    "Powering_Up": bool(status_byte & 0x40),
                    "RAM_Check_Error": bool(status_byte & 0x80)
                }

                # Determine the status code and message based on the status byte
                if response["data"]["Emergency_Off"] or response["data"]["Emergency_Stop"] or response["data"]["RAM_Check_Error"]:
                    response["status_code"] = 500
#                    response["message"] = "Internal Server Error"
                elif response["data"]["Service_Mode"] or response["data"]["Powering_Up"]:
                    response["status_code"] = 503
#                    response["message"] = "Service Unavailable"
                elif response["data"]["Ready"]:
                    response["status_code"] = 200
#                    response["message"] = "Ready"
                else:
                    response["status_code"] = 200
#                    response["message"] = "Command Station Status OK"

            # Handle known sequences
            elif chunk[0] == 0x63 and chunk[1] == 0x21 and len(chunk) >= 3:
                version_byte = chunk[2]
                version_number = version_byte / 100.0
                response["status_code"] = 200  # OK
                response["message"] = "controller"
                response["data"] = {
                    "Make": "Hornby",
                    "Model": "Elite",
                    "Version": f"{version_number:.2f}"
                }

            elif chunk[:3] == b'\x61\x00\x61':
                response["status_code"] = 500  # Server Error
                response["message"] = "Track power off"

            elif chunk[:3] == b'\x61\x01\x60':
                response["status_code"] = 100  # Continue
                response["message"] = "Normal operations resumed"

            elif chunk[:3] == b'\x81\x00\x81':
                response["status_code"] = 500  # Server Error
                response["message"] = "Emergency off"

            elif chunk[:3] == b'\x61\x02\x63':
                response["status_code"] = 503  # Service Unavailable
                response["message"] = "In service mode"

            elif chunk[:3] == b'\x01\x04\x05':
                response["status_code"] = 200  # Server Error
                response["message"] = "Command OK"

            elif chunk[:2] == b'\x61\x80':
                response["status_code"] = 400  # Bad Request
                response["message"] = "Transmission error"

            elif chunk[:2] == b'\x61\x81':
                response["status_code"] = 503  # Service Unavailable
                response["message"] = "Command station busy"

            elif chunk[:2] == b'\x61\x82':
                response["status_code"] = 400  # Bad Request
                response["message"] = "Command not supported"

            else:
                response["status_code"] = 520  # Unknown Error
                response["message"] = f"Unknown data: {to_hex(chunk)}"

            # Convert the response to JSON
            json_message = json.dumps(response)

            # Call the callback function if available
            if callback and response["message"]:
                callback(json_message)

            buffer = buffer[chunk_size:]  # Remove the processed chunk from the buffer
        else:
            # If there aren't enough bytes yet, wait for more data to arrive
            break

# Listen for incoming serial data
def listen_serial():
    receive()

# Connection management
def connection_open(device, baud, delay, cb=None):
    global ser, delay_between_commands, callback, listening
    try:
        ser = serial.Serial(device, baud)
        ser.timeout = 1.0  # 1-second timeout for reads
        delay_between_commands = delay
        callback = cb  # Set the callback function
        listening = True
        generate_function_table()

        logging.debug("Serial connection opened")

        listen_thread = threading.Thread(target=listen_serial)
        listen_thread.daemon = True
        listen_thread.start()
    except Exception as e:
        logging.error(f"Failed to open serial connection: {e}")

def connection_close():
    global ser, listening
    logging.debug("Closing serial connection")
    listening = False  # Signal the thread to stop
    if ser and ser.is_open:
        ser.close()
        ser = None

# Get version command
def getVersion():
    get_version = [0x21, 0x21]
    send(get_version)

# Get status command
def getStatus():
    get_status = [0x21, 0x24]
    send(get_status)

# Emergency Off Request
def emergencyOff():
    emergency_off = [0x21, 0x80]
    send(emergency_off)

# Emergency Off Request
def resumeNormalOperations():
    resume_normal_operations = [0x21, 0x81]
    send(resume_normal_operations)

def generate_function_table():
    global function_table
    function_table = []
    # Special case for Function 0 (F0) in Group 0
    function_table.append([0, 0x20, 0x10])
    # Group 0 (F0-F4)
    function_table.extend([[0, 0x20, 1 << i] for i in range(4)])
    # Group 1 (F5-F12)
    function_table.extend([[1, 0x21, 1 << i] for i in range(4)])
    # Group 2 (F9-F12)
    function_table.extend([[2, 0x22, 1 << i] for i in range(4)])
    # Group 3 (F13-F20)
    function_table.extend([[3, 0x23, 1 << i] for i in range(8)])
    # Group 4 (F21-F28)
    function_table.extend([[4, 0x28, 1 << i] for i in range(8)])

# Train control class
class Train:
    def __init__(self, address):
        self.address = address
        self.group = [0, 0, 0, 0, 0]  # Initialize the state of function groups (F0-F28)
        self.speed = 0
        self.direction = FORWARD

    def getState(self):
        global last_requested_train_address, first_response_processed
        # Set the global variable to the current train address
        last_requested_train_address = self.address
        first_response_processed = False  # Reset the flag

        # Construct the function states (first part)
        message = bytearray(b'\xE3\x00\x00\x00')
        struct.pack_into(">H", message, 2, self.address)
        xor_byte = calculate_checksum(message)
        message.append(xor_byte)
        send(message)

        # Construct the function states (second part)
        message = bytearray(b'\xE3\x08\x00\x00')
        struct.pack_into(">H", message, 2, self.address)
        xor_byte = calculate_checksum(message)
        message.append(xor_byte)
        send(message)


    def throttle(self, speed, direction):
        self.speed = speed
        self.direction = direction

        message = bytearray(b'\xE4\x00\x00\x00\x00')
        message[1] = 0x13
        struct.pack_into(">H", message, 2, self.address)
        message[4] = speed
        if direction == FORWARD:
            message[4] |= 0x80
        elif direction == REVERSE:
            message[4] &= 0x7F

        # Calculate the XOR byte (checksum) using the global function
        xor_byte = calculate_checksum(message)
        message.append(xor_byte)

        send(message)

    # The Hornby ELITE does not support emergency stop of a locomotive, so do not set a deceleration rate in the decoder
    def stop(self):
        self.throttle(0,self.direction)
        #message = bytearray(b'\x92\x00\x00')
        #struct.pack_into(">H", message, 1, self.address)
        #xor_byte = calculate_checksum(message)
        #message.append(xor_byte)
        #send(message)

    def function(self, num, switch):
        if num >= len(function_table):
            raise RuntimeError('Invalid function')

        group_index, header_byte, bitmask = function_table[num]
        message = bytearray(b'\xE4\x00\x00\x00\x00')
        message[1] = header_byte

        if switch == ON:
            self.group[group_index] |= bitmask  # Turn on the function
        elif switch == OFF:
            self.group[group_index] &= ~bitmask  # Turn off the function
        else:
            raise RuntimeError('Invalid switch on function')

        message[4] = self.group[group_index]
        struct.pack_into(">H", message, 2, self.address)

        # Calculate the XOR byte (checksum) using the global function
        xor_byte = calculate_checksum(message)
        message.append(xor_byte)

        send(message)

    def update_throttle(self, speed, direction):
        self.speed = speed
        self.direction = direction

    def update_functions(self, functions):
    # Update each function's state based on the received data
        for i in range(29):  # Loop through all functions F0-F28
            if str(i) in functions:
                state = functions[str(i)]
                group_index, _, bitmask = function_table[i]  # Retrieve correct group index and bitmask

                if state:
                    self.group[group_index] |= bitmask  # Turn on the function
                else:
                    self.group[group_index] &= ~bitmask  # Turn off the function

class Accessory:
    def __init__(self, address):
        self.offset = address % 4
        self.address = address // 4

    # The following two functions switch turnouts.
    # Output 1 is reverse on the hornby elite
    def activateOutput1(self):
        message = bytearray(b'\x52\x00\x00')
        message[1] = self.address
        #Set activate bit and set output to 1
        message[2] = 0x80
        #Set offset bits
        message[2] |= (self.offset & 0x03) << 1

        xor_byte = calculate_checksum(message)
        message.append(xor_byte)

        send(message)

    # Output 2 is forward on the hornby elite
    def activateOutput2(self):
        message = bytearray(b'\x52\x00\x00')
        message[1] = self.address
        #Set activate bit and set output to 2
        message[2] = 0x81
        #Set offset bits
        message[2] |= (self.offset & 0x03) << 1

        xor_byte = calculate_checksum(message)
        message.append(xor_byte)

        send(message)

class XpressNetException(Exception):
    pass
