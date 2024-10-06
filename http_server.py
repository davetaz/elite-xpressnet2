import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
import os

class MyHTTPServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, controller_getter, local_ip):
        super().__init__(server_address, RequestHandlerClass)
        self.get_controller = controller_getter
        self.local_ip = local_ip

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Prepare the response data
        hostname = socket.gethostname()
        local_ip = self.server.local_ip
        websocket_port = 8080
        controller = self.server.get_controller()  # Use the getter function
        controller_status = "Connected" if controller is not None else "Not Connected"

        response = f"""
        <html>
            <head><title>xpressNet Control</title></head>
            <body>
                <h1>xpressNet Control Status</h1>
                <p><strong>Hostname:</strong> {hostname}</p>
                <p><strong>Local IP:</strong> {local_ip}</p>
                <p><strong>WebSocket Port:</strong> {websocket_port}</p>
                <p><strong>Controller Status:</strong> {controller_status}</p>
                <form method="POST" action="/emergencyOff">
                    <button type="submit">Emergency Off</button>
                </form>
                <form method="POST" action="/resumeNormalOperations">
                    <button type="submit">Resume Normal Operations</button>
                </form>
        """

        # Check if TRAIN_3_TEST_ENABLE is set to TRUE
        if os.getenv("TRAIN_3_TEST_ENABLE", "FALSE").upper() == "TRUE":
            response += """
                <h2>Train 3 Control Test</h2>
                <form method="POST" action="/train3Forward">
                    <button type="submit">Forward - Speed 40</button>
                </form>
                <form method="POST" action="/train3Reverse">
                    <button type="submit">Reverse - Speed 40</button>
                </form>
                <form method="POST" action="/train3Stop">
                    <button type="submit">Stop</button>
                </form>
                <form method="POST" action="/f0On">
                    <button type="submit">f0 - On</button>
                </form>
                <form method="POST" action="/f0Off">
                    <button type="submit">f0 - Off</button>
                </form>
            """

        # Check if ACCESSORY_4_TEST_ENABLE is set to TRUE
        if os.getenv("ACCESSORY_4_TEST_ENABLE", "FALSE").upper() == "TRUE":
            response += """
                <h2>Accessory 4 Control</h2>
                <form method="POST" action="/accessory4Forward">
                    <button type="submit">Accessory 4 Forward</button>
                </form>
                <form method="POST" action="/accessory4Reverse">
                    <button type="submit">Accessory 4 Reverse</button>
                </form>
            """

        response += """
            </body>
        </html>
        """

        # Send response
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(response.encode('utf-8'))

    def do_POST(self):
        controller = self.server.get_controller()  # Use the getter function
        if controller is not None:
            if self.path == '/emergencyOff':
                print("Emergency Off triggered via web interface.")
                controller.emergencyOff()
            elif self.path == '/resumeNormalOperations':
                print("Resume Normal Operations triggered via web interface.")
                controller.resumeNormalOperations()
            elif self.path == '/train3Forward':
                print(f"Train 3 Throttle forward: Speed 40")
                controller.throttle(3, 40, 1)
            elif self.path == '/train3Reverse':
                print(f"Train 3 Throttle reverse: Speed 40")
                controller.throttle(3, 40, 0)
            elif self.path == '/train3Stop':
                print(f"Train 3: Stop")
                controller.stop(3)
            elif self.path == '/f0On':
                print("Train 3 f0 - On triggered via web interface.")
                controller.function(3, 0, True)
            elif self.path == '/f0Off':
                print("Train 3 f0 - Off triggered via web interface.")
                controller.function(3, 0, False)
            elif self.path == '/accessory4Forward':
                print("Accessory 4 Forward triggered via web interface.")
                controller.setAccessoryState(4, "FORWARD")
            elif self.path == '/accessory4Reverse':
                print("Accessory 4 Reverse triggered via web interface.")
                controller.setAccessoryState(4, "REVERSE")

        # Redirect back to the main page
        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()

def start_http_server(controller_getter, local_ip):
    http_port = int(os.getenv("HTTP_SERVER_PORT", 80))
    server = MyHTTPServer(('0.0.0.0', http_port), RequestHandler, controller_getter, local_ip)
    print(f"HTTP server started on port {http_port}")
    server.serve_forever()