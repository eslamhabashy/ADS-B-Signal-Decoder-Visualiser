from http.server import BaseHTTPRequestHandler
import json
import sys
import os

# Adjust import path to find local modules in the parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from decoder import decode_airborne_position

class handler(BaseHTTPRequestHandler):
    
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        
        try:
            params = json.loads(post_data.decode("utf-8"))
        except Exception:
            self.send_error_response("Invalid JSON data.")
            return

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

    def send_success_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def send_error_response(self, error_msg):
        self.send_response(200)  # Standard response with error payload
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": error_msg}).encode("utf-8"))
