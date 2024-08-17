import logging
import serial
import threading
import struct
from functools import reduce
import json

# Constants for direction
FORWARD = 0
REVERSE = 1
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

import json
import struct

def decode_loco_address(high_byte, low_byte):
    if high_byte < 0xC0:  # Addresses less than 100
        return low_byte
    else:  # Addresses from 100 to 9999
        return ((high_byte & 0x3F) << 8) | low_byte

# Process received data
def process_data():
    global buffer
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

            # Handle Loco Status Message (Function and Speed/Direction)
            if chunk[0] == 0xE5 and len(chunk) >= 7:
                print()
                identification_byte = chunk[1]

                # Extract Loco Address
                loco_address = decode_loco_address(chunk[2], chunk[3])

                if identification_byte == 0xF9:
                    # Function message
                    response["message"] = "Loco Function Status"
                    response["data"]["loco_address"] = loco_address

                    # Decode Function Group 1 and Group 2 states
                    function_group_1 = chunk[4]
                    function_group_2 = chunk[5]

                    # Decode Function Group 1 (F0-F4) and Function Group 2 (F5-F12)
                    function_group_1 = chunk[4]
                    function_group_2 = chunk[5]

                    response["data"]["functions"] = {
                        "F0": bool(function_group_1 & 0x10),
                        "F1": bool(function_group_1 & 0x01),
                        "F2": bool(function_group_1 & 0x02),
                        "F3": bool(function_group_1 & 0x04),
                        "F4": bool(function_group_1 & 0x08),
                        "F5": bool(function_group_2 & 0x01),
                        "F6": bool(function_group_2 & 0x02),
                        "F7": bool(function_group_2 & 0x04),
                        "F8": bool(function_group_2 & 0x08),
                        "F9": bool(function_group_2 & 0x10),
                        "F10": bool(function_group_2 & 0x20),
                        "F11": bool(function_group_2 & 0x40),
                        "F12": bool(function_group_2 & 0x80),
                    }

                elif identification_byte == 0xF8:
                    # Speed and direction message
                    response["message"] = "Loco Speed/Direction Status"
                    response["data"]["loco_address"] = loco_address
                    # Additional decoding for speed and direction can go here

            # Handle Command Station Status Response (200 OK)
            elif chunk[0] == 0x62 and chunk[1] == 0x22 and len(chunk) >= 3:
                status_byte = chunk[2]
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
                    response["message"] = "Internal Server Error"
                elif response["data"]["Service_Mode"] or response["data"]["Powering_Up"]:
                    response["status_code"] = 503
                    response["message"] = "Service Unavailable"
                elif response["data"]["Ready"]:
                    response["status_code"] = 200
                    response["message"] = "Ready"
                else:
                    response["status_code"] = 200
                    response["message"] = "Command Station Status OK"

            # Handle known sequences
            elif chunk[0] == 0x63 and chunk[1] == 0x21 and len(chunk) >= 3:
                version_byte = chunk[2]
                version_number = version_byte / 100.0
                response["status_code"] = 200  # OK
                response["message"] = "Hornby Elite - Version"
                response["data"] = {"version": f"{version_number:.2f}"}

            elif chunk[:3] == b'\x61\x00\x61':
                response["status_code"] = 500  # Server Error
                response["message"] = "Track power off"

            elif chunk[:3] == b'\x61\x00\x61':
                response["status_code"] = 100  # Continue
                response["message"] = "Normal operations resumed"

            elif chunk[:3] == b'\x81\x00\x81':
                response["status_code"] = 500  # Server Error
                response["message"] = "Emergency off"

            elif chunk[:3] == b'\x61\x02\x63':
                response["status_code"] = 503  # Service Unavailable
                response["message"] = "In service mode"

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

def connection_close():
    global ser, listening
    logging.debug("Closing serial connection")
    listening = False  # Signal the thread to stop
    if ser and ser.is_open:
        ser.close()
        ser = None

def generate_function_table():
    global function_table
    function_table = []
    # Special case for Function 0 (F0) in Group 0
    function_table.append([0, 0x20, 0x10])
    # Group 0 (F0-F4)
    function_table.extend([[0, 0x20, 1 << i] for i in range(4)])
    # Group 1 (F5-F8)
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
        self.group = [0, 0, 0, 0, 0]  # Initialize the state of function groups

    def throttle(self, speed, direction):
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

    def stop(self):
        message = bytearray(b'\x92\x00\x00')
        struct.pack_into(">H", message, 1, self.address)

        # Calculate the XOR byte (checksum) using the global function
        xor_byte = calculate_checksum(message)
        message.append(xor_byte)

        send(message)

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

# Get version command
def getVersion():
    get_version = [0x21, 0x21]
    send(get_version)

# Get status command
def getStatus():
    get_status = [0x21, 0x24]
    send(get_status)

class XpressNetException(Exception):
    pass