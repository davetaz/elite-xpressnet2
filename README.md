# xpressNet Control

xpressNet Control is a utility for managing and controlling the **Hornby Elite** digital command control (DCC) system using the **xpressNet protocol**. It provides **WebSocket** and **HTTP interfaces** for seamless control of trains and accessories from a Raspberry Pi.

---

## Features

- Control trains and accessories using WebSocket and HTTP APIs.
- Supports Hornby Elite controllers via xpressNet.
- Provides a systemd service for easy management.
- Includes an mDNS service for network discovery.

---

## Installation Guide

### Step 1: Prepare a Raspberry Pi SD Card

1. Download **Raspberry Pi Imager** from the [official website](https://www.raspberrypi.com/software/).
2. Insert an SD card into your computer.
3. Open Raspberry Pi Imager and:
   - Choose an OS (e.g., **Raspberry Pi OS Lite** for a headless setup).
   - Configure advanced options (click the ⚙️ icon):
     - Set a hostname (e.g., `xpressnet-control`).
     - Enable SSH.
     - Set your username and password.
   - Select your SD card and click **Write**.
4. Insert the SD card into your Raspberry Pi and boot it up.

---

### Step 2: Install Dependencies

1. SSH into your Raspberry Pi:
   ```bash
   ssh pi@<hostname>.local
   ```
   Replace `<hostname>` with the name you set in Raspberry Pi Imager.

2. Update the system and install dependencies:
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install python3 python3-pip python3-serial python3-dotenv python3-websockets python3-zeroconf avahi-utils -y
   ```

---

### Step 3: Download and Install the Package

1. Download the `.deb` package from the [latest release](https://github.com/username/repo/releases):
   ```bash
   wget https://github.com/username/repo/releases/download/v1.0.0/xpressnet-control-1.0.0.deb
   ```

2. Install the package:
   ```bash
   sudo apt install ./xpressnet-control-1.0.0.deb
   ```

3. Verify the service is running:
   ```bash
   sudo systemctl status xpressnet-control
   ```

   Expected output:
   ```
   ● xpressnet-control.service - xpressNet Control Service
      Loaded: loaded (/etc/systemd/system/xpressnet-control.service; enabled)
      Active: active (running)
   ```

---

### Step 4: Run the Source Code (Standalone Mode)

The source code is installed in `/usr/lib/xpressnet-control`. You can run it directly as a standalone Python application:

1. Navigate to the source directory:
   ```bash
   cd /usr/lib/xpressnet-control
   ```

2. Run the `socket-server.py` script:
   ```bash
   python3 socket-server.py
   ```

This will start the WebSocket and HTTP interfaces without using the systemd service.

---

## Usage

### Controlling the Service

- Start the service:
  ```bash
  sudo systemctl start xpressnet-control
  ```

- Stop the service:
  ```bash
  sudo systemctl stop xpressnet-control
  ```

- Restart the service:
  ```bash
  sudo systemctl restart xpressnet-control
  ```

- View the logs:
  ```bash
  sudo journalctl -u xpressnet-control
  ```

### Accessing the Web Interface

1. Open a browser and navigate to:
   ```
   http://<hostname>.local:8081
   ```
   Replace `<hostname>` with the Raspberry Pi's hostname.

2. Use the interface to control trains and accessories.

---

## Configuration

The main configuration file is located at:
```plaintext
/etc/xpressnet-control/xpressnet-control.conf
```

You can edit this file to change settings like HTTP server port and enable/disable test features.

Example:
```plaintext
HTTP_SERVER_ENABLE=TRUE
HTTP_SERVER_PORT=8081
TRAIN_3_TEST_ENABLE=TRUE
ACCESSORY_4_TEST_ENABLE=TRUE
```

After making changes, restart the service:
```bash
sudo systemctl restart xpressnet-control
```

---

## Troubleshooting

### Zeroconf Error: `NonUniqueNameException`
If you encounter a `NonUniqueNameException`, another instance of the service is already running or the service name is taken on the network. Restart the service or edit the `start_mdns_advertising` function in `socket-server.py` to allow name changes.

---

## Contributing

1. Fork the repository.
2. Create a feature branch:
   ```bash
   git checkout -b feature-name
   ```
3. Commit your changes and push to GitHub.
4. Submit a pull request.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Author

**David Tarrant**