#!/usr/bin/env python3
"""
ADS-B Signal Decoder Visualiser Launcher

This script starts a local web server (http://localhost:8080) and opens a browser
to display the interactive flight instrumentation and map dashboard. It loads
the HTML from index.html and maps the API endpoints.
"""

import http.server
import socketserver
import json
import webbrowser
import sys
import os
from typing import Dict, Any

# Ensure we can import decoder and parser from local path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from decoder import decode_airborne_position, decode_airborne_velocity

PORT = 8080

class ADSBVisualiserHTTPHandler(http.server.BaseHTTPRequestHandler):
    
    def log_message(self, format: str, *args: Any) -> None:
        # Override to suppress console spam from HTTP requests
        pass

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            try:
                html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
                with open(html_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error loading index.html: {str(e)}".encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        
        try:
            params = json.loads(post_data.decode("utf-8"))
        except Exception:
            self.send_error_response("Invalid JSON data.")
            return

        if self.path == "/api/decode_position":
            self.handle_decode_position(params)
        elif self.path == "/api/decode_velocity":
            self.handle_decode_velocity(params)
        else:
            self.send_response(404)
            self.end_headers()

    def handle_decode_position(self, params: Dict[str, Any]) -> None:
        even_msg = params.get("even_msg", "")
        odd_msg = params.get("odd_msg", "")
        
        if not even_msg or not odd_msg:
            self.send_error_response("Both Even and Odd messages are required.")
            return
            
        try:
            res = decode_airborne_position(even_msg, odd_msg)
            self.send_success_response(res)
        except Exception as e:
            self.send_error_response(str(e))

    def handle_decode_velocity(self, params: Dict[str, Any]) -> None:
        hex_msg = params.get("hex_msg", "")
        
        if not hex_msg:
            self.send_error_response("Velocity hex message is required.")
            return
            
        try:
            res = decode_airborne_velocity(hex_msg)
            self.send_success_response(res)
        except Exception as e:
            self.send_error_response(str(e))

    def send_success_response(self, data: Dict[str, Any]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def send_error_response(self, error_msg: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": error_msg}).encode("utf-8"))


def start_server() -> None:
    handler = ADSBVisualiserHTTPHandler
    socketserver.TCPServer.allow_reuse_address = True
    
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print("-" * 65)
        print(f"ADS-B Visualiser Server launched locally on: http://localhost:{PORT}")
        print("Press Ctrl+C to terminate.")
        print("-" * 65)
        
        # Open default browser automatically
        webbrowser.open(f"http://localhost:{PORT}")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            httpd.shutdown()


if __name__ == "__main__":
    start_server()
