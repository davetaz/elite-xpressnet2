import xpressNet
import time

# Define a callback function to handle messages
def handle_message(message):
    print(f"{message}")

# Open connection
xpressNet.connection_open('/dev/ttyACM0', 19200, 0.25, handle_message)

# Request software version
xpressNet.getVersion()

# Request command station status
xpressNet.getStatus()

train = xpressNet.Train(103)  # Initialize a train with address 0x03
time.sleep(5)
print('Function 1 on')
train.function(1, xpressNet.ON )  # Turn on function 1 in group 0
time.sleep(5)
print('Function 2 on')
train.function(2, xpressNet.ON )  # Turn on function 1 in group 0
time.sleep(0.25)
print('Function 2 off')
train.function(2, xpressNet.OFF )  # Turn on function 1 in group 0
time.sleep(5)
print('Function 1 off')
train.function(1, xpressNet.OFF )  # Turn on function 1 in group 0
a = xpressNet.Accessory(5)
time.sleep(2)
print('switch point 1')
a.activateOutput2()
time.sleep(3)
print('switch point 2')
a.activateOutput1()



try:
    # Main loop, keep the program running until interrupted
    while True:
        time.sleep(1)  # Keeping the main thread alive, but not busy
except KeyboardInterrupt:
    # Handle the keyboard interrupt to close the connection and terminate the program
    print("Terminating program...")
    xpressNet.connection_close()
    print("Program terminated.")
